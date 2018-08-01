# Overview
**Caution:** This project is far from feature complete! Don't use it in production.
Anyways I'm looking forward to receive some great PRs to make it more stable or complete :-)

The wsrtunnel project is a reverse tunnel / proxy for HTTP requests. For example it can be used to access REST services which are
located behind a strict firewall.

As long as HTTP / HTTPS connection to the outside are allowed (even through a proxy), it should be possible to create a 
websocket connection which can then be used to receive incoming requests for the target service.

## Architecture
The project consists mostly of two important parts:

### Gateway Server
You will access this server with your REST requests. Basically almost any HTTP request you throw at it, will be forwarded to the connected gateway client.

### Gateway Client
This client builds the tunnel connection with the gateway server. Therefore it connects to a special URL (`/_ws`) and keeps
the websocket connection open to receive requests.

When it receives a request, it will open a connection with the specified target service and forwards the request. After 
receiving a response it will then be send back to the gateway server.

# Deployment

## Requirements
* Python 3.7 (uses dataclass)
* aiohttp (async http client / server)

## Build
```
docker build -t wsrtunnel:latest .
```

## Run
### Server

The docker container runs an nginx webserver, listening on two different ports:
- Port 5000 (HTTPS): The websocket endpoint (configurable)
- Port 80 (HTTP): The exposed service

```
docker run -p 5000:5000 -p 6000:5001 -v "c:/letsencrypt:/etc/letsencrypt" -it wsrtunnel:latest
```

Please remember to set the following environment variables:
* `NGINX_WEBSOCKET_HOST`: Your server hostnames (also relevant for SSL certificates), e.g. `mydomain1.com mydomain2.com`
* `NGINX_WEBSOCKET_PORT`: Your server SSL port (e.g. `5000`)
* `NGINX_WEBSOCKET_SSL_CERTIFICATE`: E.g `/etc/letsencrypt/live/mydomain1.com/fullchain.pem`
* `NGINX_WEBSOCKET_SSL_CERTIFICATE_KEY`: E.g `/etc/letsencrypt/live/mydomain1.com/privkey.pem`

## Other info
### Install requirements behind proxy
```
pip --proxy http://myproxyhost:8080 --trusted-host pypi.org --trusted-host files.pythonhosted.org install aiohttp
```

Alternatively, create a file (Windows) under C:\Users\yourusername\pip\pip.ini with the following content
```
[global]
trusted-host = pypi.python.org
               pypi.org
               files.pythonhosted.org
proxy = http://yourproxyhost:8080
```

### Regenerate SSL certificates
This docker container exposes ports 80 / 443. Make sure they are reachable under the domains you want to certify.

```
docker run --rm -p 443:443 -p 80:80 --name letsencrypt -v "c:/letsencrypt:/etc/letsencrypt" -v "c:/letsencrypt/lib:/var/lib/letsencrypt" -it certbot/certbot certonly --standalone
```
