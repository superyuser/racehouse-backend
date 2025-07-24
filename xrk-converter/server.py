from flask import Flask, request, send_file, jsonify
import os
import subprocess
import uuid
import shutil
import copy
import sys
import traceback
import time
import datetime

app = Flask(__name__)

# Configuration
MATLAB_RUNTIME_ROOT = r'C:\Program Files\MATLAB\MATLAB Runtime\R2024b'
MATLAB_SUBDIRS = [
    r'runtime\win64',
    r'bin\win64',
    r'sys\os\win64',  # Uncommented - needed for DLL loading
    r'sys\win64',
]
COMPILED_DIR = os.path.abspath('compiled')
TMP_ROOT = os.path.abspath('tmp')
OUTPUT_DIR = os.path.abspath('output')
MAX_UPLOAD_SIZE_MB = 100

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE_MB * 1024 * 1024

def copy_compiled_files(compiled_dir, base_dir):
    # First ensure the base directory exists
    os.makedirs(base_dir, exist_ok=True)
    
    # Track what files were copied for debugging
    copied_files = []
    
    for root, _, files in os.walk(compiled_dir):
        rel_path = os.path.relpath(root, compiled_dir)
        dest_dir = os.path.join(base_dir, rel_path)
        os.makedirs(dest_dir, exist_ok=True)
        
        for file in files:
            # Copy all important files including DLLs
            if file.endswith(('.exe', '.dll', '.h', '.m', '.ctf', '.xml')):
                src_file = os.path.join(root, file)
                dst_file = os.path.join(dest_dir, file)
                shutil.copy2(src_file, dst_file)
                copied_files.append(os.path.relpath(dst_file, base_dir))
    
    print(f"✅ Copied {len(copied_files)} files to {base_dir}")
    return copied_files

def build_runtime_env():
    env = copy.deepcopy(os.environ)
    
    # Add current directory to PATH to find local DLLs
    env['PATH'] = os.getcwd() + os.pathsep + env.get('PATH', '')
    
    # Check if MATLAB Runtime paths exist and add them
    existing_paths = []
    for subdir in MATLAB_SUBDIRS:
        full_path = os.path.join(MATLAB_RUNTIME_ROOT, subdir)
        if os.path.exists(full_path):
            existing_paths.append(full_path)
        else:
            print(f"⚠️ MATLAB Runtime path not found: {full_path}")
    
    # Prepend all MATLAB paths at once (order matters for DLL dependencies)
    if existing_paths:
        env['PATH'] = os.pathsep.join(existing_paths) + os.pathsep + env['PATH']
        print(f"✅ Added {len(existing_paths)} MATLAB Runtime paths")
    else:
        print("⚠️ No MATLAB Runtime paths found")
        
    return env

@app.route('/convert', methods=['POST'])
def convert_xrk():
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    # Create unique session directory
    session_id = str(uuid.uuid4())
    session_dir = os.path.join(TMP_ROOT, session_id)
    os.makedirs(session_dir, exist_ok=True)

    # Save uploaded XRK file
    file = request.files['file']
    input_path = os.path.join(session_dir, file.filename)
    file.save(input_path)

    # Copy all required compiled files recursively
    copy_compiled_files(COMPILED_DIR, session_dir)

    # Run MATLAB-compiled executable
    exe_path = os.path.join(session_dir, 'main.exe')
    env = build_runtime_env()
    
    # Print current working directory and PATH for debugging
    print(f"Working directory: {session_dir}")
    print(f"EXE path: {exe_path}")
    print(f"Exists: {os.path.exists(exe_path)}")
    
    # Start timer for conversion
    start_time = time.time()

    try:
        # Change working directory to session_dir first to help with DLL loading
        original_dir = os.getcwd()
        os.chdir(session_dir)
        
        result = subprocess.run(
            [exe_path],
            cwd=session_dir,  # Still set cwd for subprocess
            env=env,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        # Return to original directory
        os.chdir(original_dir)
        
        # Calculate conversion time
        conversion_time = time.time() - start_time
        print(f"⏱️ Conversion completed in {conversion_time:.2f} seconds")
    except Exception as e:
        os.chdir(original_dir)  # Make sure we return to original dir even on error
        print(f"Error running executable: {e}")
        traceback.print_exc()
        return jsonify({
            'error': f'Failed to run MATLAB executable: {str(e)}',
        }), 500

    print("STDOUT:\n", result.stdout)
    print("STDERR:\n", result.stderr)

    if result.returncode != 0:
        # Calculate time even on failure
        conversion_time = time.time() - start_time
        print(f"⏱️ Conversion failed after {conversion_time:.2f} seconds")
        
        return jsonify({
            'error': 'MATLAB execution failed',
            'stdout': result.stdout,
            'stderr': result.stderr,
            'conversion_time': f"{conversion_time:.2f} seconds"
        }), 500

    # Locate output data
    output_dir = os.path.join(session_dir, 'data')
    if not os.path.isdir(output_dir):
        return jsonify({'error': 'No output directory created'}), 500

    output_files = [
        os.path.join(output_dir, f)
        for f in os.listdir(output_dir)
        if os.path.isfile(os.path.join(output_dir, f))
    ]

    if not output_files:
        return jsonify({'error': 'No output file generated'}), 500

    # Calculate final conversion time including file processing
    conversion_time = time.time() - start_time
    print(f"⏱️ Total processing completed in {conversion_time:.2f} seconds")
    
    # If there's only one file, return it directly
    if len(output_files) == 1:
        # Create timestamp and filename
        timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
        original_filename = os.path.splitext(file.filename)[0]
        output_ext = os.path.splitext(output_files[0])[1]
        
        # Create unique filename with timestamp
        output_filename = f"{original_filename}_{timestamp}{output_ext}"
        
        # Create output directory if it doesn't exist
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        
        # Copy file to output directory
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        shutil.copy2(output_files[0], output_path)
        print(f"✅ Saved output to {output_path}")
        
        # Send the file
        response = send_file(output_files[0], as_attachment=True)
        response.headers['X-Conversion-Time'] = f"{conversion_time:.2f} seconds"
        response.headers['X-Output-Path'] = output_path
        return response

    # Else, zip and send all
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    original_filename = os.path.splitext(file.filename)[0]
    
    # Create unique filename with timestamp
    output_filename = f"{original_filename}_{timestamp}.zip"
    
    # Create output directory if it doesn't exist
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    # Path for temporary zip and final output zip
    temp_zip_path = session_dir + '.zip'
    final_zip_path = os.path.join(OUTPUT_DIR, output_filename)
    
    # Create the zip file
    shutil.make_archive(session_dir, 'zip', output_dir)
    
    # Copy the zip to output directory with timestamp filename
    shutil.copy2(temp_zip_path, final_zip_path)
    print(f"✅ Saved output to {final_zip_path}")
    
    # Add conversion time to response headers
    response = send_file(temp_zip_path, as_attachment=True)
    response.headers['X-Conversion-Time'] = f"{conversion_time:.2f} seconds"
    response.headers['X-Output-Path'] = final_zip_path
    return response

if __name__ == '__main__':
    # Ensure temporary and output directories exist
    os.makedirs(TMP_ROOT, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    print(f"✅ Output directory setup at: {OUTPUT_DIR}")
    
    # Check MATLAB Runtime configuration
    print("Checking MATLAB Runtime configuration...")
    env = build_runtime_env()
    
    # Clean temporary folders from previous runs
    print("Cleaning old temporary folders...")
    for item in os.listdir(TMP_ROOT):
        item_path = os.path.join(TMP_ROOT, item)
        if os.path.isdir(item_path):
            try:
                shutil.rmtree(item_path)
                print(f"Removed old session: {item}")
            except Exception as e:
                print(f"Could not remove {item}: {e}")
    
    print(f"Starting Flask server on port 5000...")
    app.run(port=5000, host='127.0.0.1')
