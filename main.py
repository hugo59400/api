import os
import logging
from flask import Flask, request, jsonify, send_file
import requests
import json
import time
from flask_mail import Mail, Message
import threading
import signal
import psutil
import tempfile

app = Flask(__name__)

# Configuration de Mailjet
MAILJET_API_KEY = '0db1e1f71a7ff521eaa2206af8a1c35d'
MAILJET_API_SECRET = 'fc3ee8b4aa9b7e10434e1cb43c5ff9c8'
CORRECT_PASSWORD = "test"

mail = Mail(app)

# URL de l'API cible
API_URL = 'https://api.webstorage-service.com/v1/devices/data'

# Utiliser le répertoire temporaire du système pour stocker les fichiers JSON et logs
temp_dir = tempfile.gettempdir()

# Chemins pour les fichiers JSON et logs
json_file_path = os.path.join(temp_dir, 'response.json')
log_file_path = os.path.join(temp_dir, 'app.log')

# Configuration du logging
logging.basicConfig(
    filename=log_file_path,
    level=logging.DEBUG,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# Logger un message d'initialisation
logging.info(f'Serveur Flask démarré. Logs écrits dans : {log_file_path}')

# Fonction pour arrêter le serveur proprement
def stop_server():
    logging.info("Arrêt du serveur Flask")
    os.kill(os.getpid(), signal.SIGINT)

# Route pour arrêter le serveur Flask
@app.route('/stop-server', methods=['POST'])
def stop():
    threading.Thread(target=stop_server).start()
    return jsonify({'message': 'Le serveur va s\'arrêter.'})

# Route principale pour faire la requête POST vers l'API
@app.route('/proxy', methods=['POST', 'GET'])
def proxy_request():
    try:
        api_key = request.args.get('api-key')
        login_id = request.args.get('login-id')
        login_pass = request.args.get('login-pass')
        remote_serial = request.args.get('remote-serial')

        unixtime_from = request.args.get('unixtime-from', default=int(time.time()) - 86400)
        unixtime_to = request.args.get('unixtime-to', default=int(time.time()))
        number = request.args.get('number', default=16000)
        data_type = request.args.get('type', default='json')
        temperature_unit = request.args.get('temperature-unit', default='device')

        try:
            unixtime_from = int(unixtime_from)
            unixtime_to = int(unixtime_to)
            number = int(number)
        except ValueError:
            return jsonify({'error': 'Les valeurs de unixtime-from, unixtime-to et number doivent être des entiers'}), 400

        if not api_key or not login_id or not login_pass or not remote_serial:
            return jsonify({'error': 'Paramètres manquants dans la requête'}), 400

        payload = {
            'api-key': api_key,
            'login-id': login_id,
            'login-pass': login_pass,
            'remote-serial': remote_serial,
            'unixtime-from': unixtime_from,
            'unixtime-to': unixtime_to,
            'number': number,
            'type': data_type,
            'temperature-unit': temperature_unit
        }

        headers = {'Content-Type': 'application/json', 'X-HTTP-Method-Override': 'GET'}
        logging.info("Payload envoyé à l'API externe : %s", payload)

        response = requests.post(API_URL, json=payload, headers=headers)
        if response.status_code != 200:
            logging.error("Erreur lors de la requête vers l'API externe : %s", response.text)
            return jsonify({'error': 'Erreur lors de la requête vers l\'API externe', 'status_code': response.status_code, 'message': response.text}), response.status_code

        api_response = response.json()

        # Sauvegarde la réponse dans un fichier JSON local
        with open(json_file_path, 'w') as json_file:
            json.dump(api_response, json_file)

        logging.info("Réponse de l'API externe sauvegardée dans %s", json_file_path)
        return jsonify(api_response)

    except Exception as e:
        logging.error("Erreur dans la route /proxy : %s", str(e))
        return jsonify({'error': str(e)}), 500

# Route pour télécharger le fichier JSON
@app.route('/download-json', methods=['GET'])
def download_json():
    try:
        if not os.path.exists(json_file_path):
            logging.warning("Le fichier response.json n'existe pas, création d'un fichier vide.")
            with open(json_file_path, 'w') as json_file:
                json.dump({}, json_file)  # Écriture d'un fichier JSON vide

        logging.info("Téléchargement du fichier JSON : %s", json_file_path)
        return send_file(json_file_path, as_attachment=False)

    except Exception as e:
        logging.error("Erreur dans la route /download-json : %s", str(e))
        return jsonify({'error': str(e)}), 500

# Route pour envoyer un e-mail d'alerte via Mailjet
@app.route('/send-alert', methods=['POST'])
def send_alert():
    data = request.get_json()
    subject = data.get('subject', 'Alerte de température élevée')
    message = data.get('message', 'La température a dépassé le seuil critique.')
    recipient = data.get('recipient')

    mailjet_url = "https://api.mailjet.com/v3.1/send"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "Messages": [
            {
                "From": {"Email": "hugocoleau07@gmail.com", "Name": "Alerte"},
                "To": [{"Email": recipient, "Name": "Destinataire"}],
                "Subject": subject,
                "TextPart": message,
                "HTMLPart": f"<h3>{message}</h3>"
            }
        ]
    }

    try:
        response = requests.post(mailjet_url, auth=(MAILJET_API_KEY, MAILJET_API_SECRET), json=payload, headers=headers)
        if response.status_code == 200:
            logging.info("E-mail envoyé avec succès à %s", recipient)
            return jsonify({'message': f'E-mail envoyé avec succès à {recipient} !'}), 200
        else:
            logging.error("Erreur lors de l'envoi de l'e-mail via Mailjet : %s", response.text)
            return jsonify({'error': f'Erreur lors de l\'envoi de l\'e-mail via Mailjet : {response.text}'}), response.status_code
    except Exception as e:
        logging.error("Erreur dans la route /send-alert : %s", str(e))
        return jsonify({'error': str(e)}), 500

# Route pour récupérer les statistiques Mailjet
@app.route('/mailjet-stats', methods=['GET'])
def get_mailjet_stats():
    try:
        url = 'https://api.mailjet.com/v3/REST/message'
        response = requests.get(url, auth=(MAILJET_API_KEY, MAILJET_API_SECRET))

        if response.status_code == 200:
            data = response.json()
            total_emails_sent = data['Total']
            logging.info("Statistiques Mailjet récupérées : %d e-mails envoyés", total_emails_sent)
            return jsonify({'total_emails_sent': total_emails_sent})
        else:
            logging.error("Erreur lors de la récupération des statistiques Mailjet : %s", response.text)
            return jsonify({'error': 'Erreur lors de la récupération des statistiques de Mailjet'}), response.status_code
    except Exception as e:
        logging.error("Erreur dans la route /mailjet-stats : %s", str(e))
        return jsonify({'error': str(e)}), 500

# Route pour vérifier si "start.exe" est en cours d'exécution
@app.route('/check-start-exe', methods=['GET'])
def check_start_exe():
    for proc in psutil.process_iter(['pid', 'name']):
        if proc.info['name'] == 'start.exe':
            return jsonify({"running": True})
    return jsonify({"running": False})

# Route pour vérifier le mot de passe
@app.route('/auth', methods=['POST'])
def auth():
    data = request.get_json()
    password = data.get('password')

    if password == CORRECT_PASSWORD:
        return jsonify({"success": True}), 200
    else:
        return jsonify({"success": False}), 403

if __name__ == '__main__':
    logging.info("Démarrage du serveur Flask")
    app.run(debug=True, port=5000, host='0.0.0.0')
