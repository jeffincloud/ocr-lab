FROM nginx:1.27-alpine

COPY public/ /usr/share/nginx/html/
COPY nginx.conf /etc/nginx/templates/default.conf.template

ENV API_HOST=ocr-api \
    API_PORT=8080

EXPOSE 80
