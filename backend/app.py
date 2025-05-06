from flask import Flask, request, jsonify
from flask_cors import CORS
import os

app = Flask(__name__)
CORS(app)

vote_file_path = '/mnt/data/votes/votes.txt'  # Write inside the mounted PVC

# Ensure the file exists on startup
if not os.path.exists(vote_file_path):
    open(vote_file_path, 'a').close()

@app.route('/vote', methods=['POST'])
def vote():
    data = request.get_json()
    choice = data.get('choice')
    name = data.get('name')

    if choice not in ['Choice 1', 'Choice 2']:
        return jsonify({"error": "Invalid choice"}), 400

    if not name or name.strip() == '':
        return jsonify({"error": "Name is required"}), 400

    with open(vote_file_path, 'a') as file:
        file.write(f"{name} voted for {choice}\n")

    return jsonify({"message": f"Vote for {choice} by {name} recorded!"})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=80)
