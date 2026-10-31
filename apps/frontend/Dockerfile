FROM docker.io/library/nginx:1.27-alpine

COPY public/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/templates/default.conf.template

# NGINX_ENTRYPOINT_LOCAL_RESOLVERS fills NGINX_LOCAL_RESOLVERS from /etc/resolv.conf.
ENV API_HOST=ocr-api \
    API_PORT=8080 \
    NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

EXPOSE 80
