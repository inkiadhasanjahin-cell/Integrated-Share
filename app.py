import os
import shutil
from datetime import datetime
from flask import Flask, render_template, request, jsonify, send_file, url_for
from werkzeug.utils import secure_filename
from flask_cors import CORS
import uuid
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import math 


app = Flask(__name__)
CORS(app)

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///files.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class SharedFile(db.Model):
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    original_name = db.Column(db.String(255), nullable=False)
    stored_name = db.Column(db.String(255), nullable=False, unique=True)
    size = db.Column(db.Integer, nullable=False)
    size_formatted = db.Column(db.String(20))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'original_name': self.original_name,
            'stored_name': self.stored_name,
            'size': self.size,
            'size_formatted': self.size_formatted,
            'uploaded_at': self.uploaded_at.timestamp(),
            'date': self.uploaded_at.strftime('%Y-%m-%d %H:%M'),
            'download_url': url_for('download_file', file_id=self.stored_name, _external=True)
        }

app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max file size
app.config['ALLOWED_EXTENSIONS'] = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'doc', 'docx', 
                                    'xls', 'xlsx', 'ppt', 'pptx', 'zip', 'rar', '7z', 'mp3', 
                                    'mp4', 'avi', 'mov', 'mkv', 'js', 'html', 'css', 'py', 
                                    'java', 'cpp', 'json', 'csv'}


# Create uploads folder if it doesn't exist
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']



def format_file_size(bytes):
    """Format file size for display"""
    if bytes == 0:
        return '0 B'
    k = 1024
    sizes = ['B', 'KB', 'MB', 'GB']
    i = int(math.floor(math.log(bytes) / math.log(k)))
    return f"{round(bytes / (k ** i), 1)} {sizes[i]}"

@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')

@app.route('/api/files', methods=['GET'])
def get_files():
    files = SharedFile.query.order_by(SharedFile.uploaded_at.desc()).all()
    return jsonify([f.to_dict() for f in files])

@app.route('/api/upload', methods=['POST'])
def upload_file():
    """Upload a new file"""
    if 'files' not in request.files:
        return jsonify({'error': 'No files provided'}), 400
    
    files = request.files.getlist('files')
    uploaded_files = []
    
    for file in files:
        if file and file.filename and allowed_file(file.filename):
            # Generate unique filename
            original_filename = secure_filename(file.filename)
            filename_parts = os.path.splitext(original_filename)
            unique_id = str(uuid.uuid4())[:8]
            unique_filename = f"{filename_parts[0]}_{unique_id}{filename_parts[1]}"
            
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
            file.save(file_path)
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Create file metadata
            file_data = {
                'id': str(uuid.uuid4()),
                'original_name': original_filename,
                'stored_name': unique_filename,
                'size': file_size,
                'size_formatted': format_file_size(file_size),
            }
            
            uploaded_files.append(file_data)
    
    if uploaded_files:
        # Load existing files and add new ones
       for file_data in uploaded_files:
            new_file = SharedFile(
                id=file_data['id'],
                original_name=file_data['original_name'],
                stored_name=file_data['stored_name'],
                size=file_data['size'],
                size_formatted=file_data['size_formatted']
            )
            db.session.add(new_file)
            db.session.commit()
            return jsonify({'success': True, 'files': uploaded_files, 'message': f'Successfully uploaded {len(uploaded_files)} file(s)'})
    else:
        return jsonify({'error': 'No valid files uploaded'}), 400
       

@app.route('/api/download/<file_id>')
def download_file(file_id):
    file_info = SharedFile.query.filter_by(stored_name=file_id).first()
    if not file_info:
        return jsonify({'error': 'File not found'}), 404
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_id)
    if not os.path.exists(file_path):
        return jsonify({'error': 'File not found on server'}), 404
    return send_file(file_path, as_attachment=True, download_name=file_info.original_name)


@app.route('/api/delete/<file_id>', methods=['DELETE'])
def delete_file(file_id):
    file_to_delete = SharedFile.query.filter_by(id=file_id).first()
    if not file_to_delete:
        return jsonify({'error': 'File not found'}), 404
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], file_to_delete.stored_name)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(file_to_delete)
    db.session.commit()
    return jsonify({'success': True, 'message': 'File deleted successfully'})

@app.route('/api/share/<file_id>', methods=['POST'])
def share_file(file_id):
    file_info = SharedFile.query.filter_by(id=file_id).first()
    if not file_info:
        return jsonify({'error': 'File not found'}), 404
    share_link = url_for('download_file', file_id=file_info.stored_name, _external=True)
    return jsonify({'success': True, 'share_link': share_link, 'message': 'Share link generated successfully'})

@app.route('/api/clear', methods=['POST'])
def clear_all_files():
    for filename in os.listdir(app.config['UPLOAD_FOLDER']):
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        try:
            if os.path.isfile(file_path):
                os.unlink(file_path)
            elif os.path.isdir(file_path):
                shutil.rmtree(file_path)
        except Exception as e:
            print(f'Failed to delete {file_path}. Reason: {e}')
    SharedFile.query.delete()
    db.session.commit()
    return jsonify({'success': True, 'message': 'All files cleared'})

if __name__ == '__main__':
    with app.app_context():
     db.create_all()
    app.run(debug=True, host='0.0.0.0', port=5000)