from flask import Flask, request, send_file
import os
import subprocess
import uuid
import shutil

app = Flask(__name__)

@app.route('/convert', methods=['POST'])
def convert_xrk():
    if 'file' not in request.files:
        return 'No file uploaded', 400

    file = request.files['file']
    session_id = str(uuid.uuid4())
    base_dir = os.path.join(os.getcwd(), 'tmp', session_id)
    os.makedirs(base_dir, exist_ok=True)

    # Save the uploaded XRK file
    xrk_path = os.path.join(base_dir, file.filename)
    file.save(xrk_path)

    # Copy required MATLAB files
    shutil.copy('AutoExportXrkData.m', base_dir)
    shutil.copy('main.m', base_dir)
    shutil.copy('AccessAimXrk.m', base_dir)
    shutil.copy('MatLabXRK-2022-64-ReleaseU.dll', base_dir)
    # Also copy dependency DLLs
    shutil.copy('libxml2-2.dll', base_dir)
    shutil.copy('libiconv-2.dll', base_dir)
    shutil.copy('pthreadVC2_x64.dll', base_dir)
    shutil.copy('libz.dll', base_dir)
    shutil.copy('MatLabXRK.h', base_dir)
    shutil.copy('helper.h', base_dir)


    # Run MATLAB batch script
    result = subprocess.run(
        ['matlab', '-batch', 'main'],
        cwd=base_dir,
        capture_output=True,
        text=True
    )

    print("STDOUT:\n", result.stdout)
    print("STDERR:\n", result.stderr)

    if result.returncode != 0:
        print("❌ MATLAB failed:", result.stderr)
        return f"MATLAB failed:\n{result.stderr}", 500

    # Create zip archive of output
    export_dir = os.path.join(base_dir, 'data')
    zip_path = f"{base_dir}.zip"
    shutil.make_archive(base_dir, 'zip', export_dir)

    return send_file(zip_path, as_attachment=True)

if __name__ == '__main__':
    os.makedirs('tmp', exist_ok=True)
    app.run(port=5000)
