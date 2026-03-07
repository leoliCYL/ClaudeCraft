RUN CLIENT
cd client && ./gradlew runClient

RUN BACKEND
pip install -r requirements.txt
cd server && source .venv/bin/activate && python main.py
