FROM python:3.10-alpine

ARG USER_NAME=app-user
RUN adduser -D -s /bin/bash $USER_NAME

# path to pip installed tools
ENV PATH="$PATH:/home/${USER_NAME}/.local/bin"
# disable bytecode files and output buffer
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# app
USER $USER_NAME
COPY ./ /app/
WORKDIR /app
RUN pip install --upgrade -r requirements.txt
ENTRYPOINT ["uvicorn", "--host", "0.0.0.0", "--port", "5000", "server:app"]
