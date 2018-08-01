FROM python:3

RUN apt-get update -y && \
    apt-get install -y python3-pip nginx supervisor gettext-base

COPY /deployment/nginx.conf.template /etc/nginx/nginx.conf.template
COPY /deployment/svd_wsrtunnel.conf /etc/supervisor/conf.d/
COPY /deployment/svd_nginx.conf /etc/supervisor/conf.d/

RUN mkdir /app
COPY /src/ /app/
COPY /requirements.txt /app/

WORKDIR /app
RUN pip3 install -r requirements.txt

CMD /bin/bash -c "DOLLAR='$' envsubst < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && supervisord -n -c /etc/supervisor/supervisord.conf"
