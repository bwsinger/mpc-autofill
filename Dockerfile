# syntax=docker/dockerfile:1
FROM python:3
ENV PYTHONUNBUFFERED=1
ENV DJANGO_DEBUG=on
WORKDIR /code/
COPY requirements.txt /code/
RUN pip install -r requirements.txt
COPY . /code/
WORKDIR /code/MPCAutofill
