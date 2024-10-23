api heberge sur render 
api publique  : https://api-naqn.onrender.com/
FRONT  :  https://app.netlify.com/sites/getinfodevices/overview

site : https://getinfodevices.netlify.app/ 

fichier python utilise par render : main.py 


start commande dans render : gunicorn main:app --bind 0.0.0.0:$PORT
