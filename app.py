from flask import Flask, render_template, request, jsonify
from backend import response
import markdown

app = Flask(__name__)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chat', methods=['POST'])
def chat():
    message = request.form['msg']
    ai_response = response(message)
    html_response = markdown.markdown(ai_response)
    print(html_response)
    return jsonify({"response": html_response})

if __name__ == '__main__':
    app.run(debug=True)
    