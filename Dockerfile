FROM python:3.14-alpine

# coreutils to use modern utils
RUN apk add coreutils curl jq

# setup user with group of docker to get access to docker socket file
ARG USER_NAME=app-user
ARG USER_GID=109
RUN adduser -D -s /bin/bash $USER_NAME && \
	addgroup -g $USER_GID docker && \
	addgroup $USER_NAME docker

# path to pip installed tools
ENV PATH="$PATH:/home/${USER_NAME}/.local/bin"
# setup lang and locale to fix date format
ENV LANG=en_US.UTF-8
# disable bytecode files and output buffer
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# cron
RUN rm /etc/crontabs/root
USER $USER_NAME
COPY ./config/crontab /etc/crontabs/$USER_NAME

# app
COPY ./ /app/
WORKDIR /app
RUN pip install --upgrade -r requirements.txt
ENTRYPOINT ["uvicorn", "--host", "0.0.0.0", "--port", "5000", "server:app"]
