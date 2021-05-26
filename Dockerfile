FROM python:3.7.10-slim-buster

ADD requirements.txt .
RUN python -m pip install -r requirements.txt

COPY trader trader
COPY main.py main.py

CMD ["python", "main.py"]
