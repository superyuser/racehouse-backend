from flask import Flask, request, send_file, jsonify
import os
import subprocess
import uuid
import shutil
import copy

app = Flask(__name__)

# Configuration
MATLAB_RUNTIME_ROOT = r'C:\Program Files\MATLAB\MATLAB Runtime\R2024b'
MATLAB_SUBDIRS = [
    r'runtime\win64',
    r'bin\win64',
    # r'sys\os\win64',  # Uncomment if needed
    # r'sys\win64',
]
COMPILED_DIR = os.path.abspath('compiled')
TMP_ROOT = os.path.abspath('tmp')
MAX_UPLOAD_SIZE_MB = 100

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_SIZE_MB * 1024 * 1024

def copy_compiled_files(compiled_dir, base_dir):
    for root, _, files in os.walk(compiled_dir):
        rel_path = os.path.relpath(root, compiled_dir)
        dest_dir = os.path.join(base_dir, rel_path)
        os.makedirs(dest_dir, exist_ok=True)
        for file in files:
            if file.endswith(('.exe', '.dll', '.h', '.m', '.ctf', '.xml')):
                src_file = os.path.join(root, file)
                dst_file = os.path.join(dest_dir, file)
                shutil.copy2(src_file, dst_file)

def build_runtime_env():
    env = copy.deepcopy(os.environ)
    for subdir in MATLAB_SUBDIRS:
        full_path = os.path.join(MATLAB_RUNTIME_ROOT, subdir)
        if os.path.exists(full_path):
            env['PATH'] += os.pathsep + full_path
        else:
            print(f"⚠️ MATLAB Runtime path not found: {full_path}")
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

    result = subprocess.run(
        [exe_path],
        cwd=session_dir,
        env=env,
        capture_output=True,
        text=True,
        encoding='utf-8',
        errors='replace'
    )

    print("STDOUT:\n", result.stdout)
    print("STDERR:\n", result.stderr)

    if result.returncode != 0:
        return jsonify({
            'error': 'MATLAB execution failed',
            'stdout': result.stdout,
            'stderr': result.stderr
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

    # If there's only one file, return it directly
    if len(output_files) == 1:
        return send_file(output_files[0], as_attachment=True)

    # Else, zip and send all
    zip_path = session_dir + '.zip'
    shutil.make_archive(session_dir, 'zip', output_dir)
    return send_file(zip_path, as_attachment=True)

if __name__ == '__main__':
    os.makedirs(TMP_ROOT, exist_ok=True)
    app.run(port=5000)
