FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Build
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx/ailab.crt /etc/nginx/ssl/ailab.crt
COPY nginx/ailab.key /etc/nginx/ssl/ailab.key
RUN echo $'server {\n\
    listen 80;\n\
    location / {\n\
        root   /usr/share/nginx/html;\n\
        index  index.html index.htm;\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    location /api/ {\n\
        proxy_pass http://api:8000/api/;\n\
        proxy_read_timeout 480s;\n\
        proxy_connect_timeout 10s;\n\
        proxy_send_timeout 480s;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        client_max_body_size 50M;\n\
    }\n\
    location /health {\n\
        proxy_pass http://api:8000/health;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    }\n\
    location /authen/ {\n\
        proxy_pass http://host.docker.internal:8001/;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    }\n\
    location /hermes/ {\n\
        proxy_pass http://host.docker.internal:9119;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto $scheme;\n\
        proxy_set_header X-Forwarded-Host $host;\n\
        proxy_read_timeout 600s;\n\
        proxy_buffering off;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
    }\n\
}\n\
# 官方 Hermes Dashboard 独立入口（根路径反代·serve 无前缀逻辑·登录正常）\n\
server {\n\
    listen 9443 ssl;\n\
    ssl_certificate     /etc/nginx/ssl/ailab.crt;\n\
    ssl_certificate_key /etc/nginx/ssl/ailab.key;\n\
    location / {\n\
        proxy_pass http://host.docker.internal:9119;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto $scheme;\n\
        proxy_set_header X-Forwarded-Host $host;\n\
        proxy_read_timeout 600s;\n\
        proxy_buffering off;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
    }\n\
}\n\
server {\n\
    listen 443 ssl;\n\
    ssl_certificate     /etc/nginx/ssl/ailab.crt;\n\
    ssl_certificate_key /etc/nginx/ssl/ailab.key;\n\
    location / {\n\
        root   /usr/share/nginx/html;\n\
        index  index.html index.htm;\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    location /api/ {\n\
        proxy_pass http://api:8000/api/;\n\
        proxy_read_timeout 480s;\n\
        proxy_connect_timeout 10s;\n\
        proxy_send_timeout 480s;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        client_max_body_size 50M;\n\
    }\n\
    location /health {\n\
        proxy_pass http://api:8000/health;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    }\n\
    location /authen/ {\n\
        proxy_pass http://host.docker.internal:8001/;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    }\n\
    location /hermes/ {\n\
        proxy_pass http://host.docker.internal:9119;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto $scheme;\n\
        proxy_set_header X-Forwarded-Host $host;\n\
        proxy_read_timeout 600s;\n\
        proxy_buffering off;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
    }\n\
    location ~* \.(html)$ {\n\
        root   /usr/share/nginx/html;\n\
        add_header Cache-Control "no-cache, no-store, must-revalidate";\n\
        add_header Pragma "no-cache";\n\
        add_header Expires 0;\n\
    }\n\
}' > /etc/nginx/conf.d/default.conf
EXPOSE 80 443 9443
CMD ["nginx", "-g", "daemon off;"]
