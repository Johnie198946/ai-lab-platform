FROM node:20-alpine AS build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
COPY apps/shared /app/apps/shared
# Build
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/frontend/dist /usr/share/nginx/html
# Quantum fork 官方 Web 引擎（web-dashboard dist → 9080 server 块；官方仓库零改动）
COPY web-dashboard/dist /usr/share/nginx/html/web-dashboard
COPY frontend/nginx/ailab.crt /etc/nginx/ssl/ailab.crt
COPY frontend/nginx/ailab.key /etc/nginx/ssl/ailab.key
RUN echo $'server {\n\
    listen 80;\n\
    return 308 https://$host$request_uri;\n\
    location / {\n\
        root   /usr/share/nginx/html;\n\
        index  index.html index.htm;\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    location /taskboard/ {\n\
        proxy_pass http://taskboard:47823/;\n\
        proxy_hide_header X-Frame-Options;\n\
        proxy_hide_header Content-Security-Policy;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Host 127.0.0.1;\n\
        proxy_set_header Origin http://127.0.0.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_read_timeout 3600s;\n\
        proxy_buffering off;\n\
        client_max_body_size 30M;\n\
        add_header X-Frame-Options "SAMEORIGIN" always;\n\
        add_header Content-Security-Policy "frame-ancestors $scheme://$host" always;\n\
        add_header X-Content-Type-Options "nosniff" always;\n\
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;\n\
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
    location = /api/chat/stream {\n\
        proxy_pass http://api:8000/api/chat/stream;\n\
        proxy_read_timeout 600s;\n\
        proxy_send_timeout 600s;\n\
        proxy_buffering off;\n\
        proxy_cache off;\n\
        proxy_request_buffering off;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    }\n\
    location = /api/showroom/ws {\n\
        proxy_pass http://api:8000/api/showroom/ws;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host $host;\n\
        proxy_read_timeout 3600s;\n\
    }\n\
    # B-2-1 最小 server 块：官方 Hermes WS 反代（精确路径优先于 /api/ → api:8000）\n\
    location = /api/ws {\n\
        proxy_pass http://host.docker.internal:9121;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host 127.0.0.1;\n\
        proxy_set_header Origin http://127.0.0.1;\n\
        proxy_read_timeout 3600s;\n\
        proxy_buffering off;\n\
    }\n\
    location = /api/pty {\n\
        proxy_pass http://host.docker.internal:9121;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host 127.0.0.1;\n\
        proxy_read_timeout 3600s;\n\
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
    location /authen-api/ {\n\
        proxy_pass http://host.docker.internal:8001/;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    }\n\
    location ^~ /hermes/ { return 404; }\n\
}\n\
# B-2-1 最小 server 块：Quantum fork 官方 Web 引擎（iOS WebContainer 入口）\n\
# location /api/ → host.docker.internal:9119（serve 无前缀逻辑；WS Upgrade 头透传）\n\
server {\n\
    listen 9080;\n\
    location / {\n\
        root   /usr/share/nginx/html/web-dashboard;\n\
        index  index.html index.htm;\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    location /api/ {\n\
        proxy_pass http://host.docker.internal:9121;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host 127.0.0.1;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto $scheme;\n\
        proxy_set_header X-Forwarded-Host $host;\n\
        proxy_read_timeout 3600s;\n\
        proxy_buffering off;\n\
    }\n\
}\n\
server {\n\
    listen 443 ssl;\n\
    ssl_certificate     /etc/nginx/ssl/ailab.crt;\n\
    ssl_certificate_key /etc/nginx/ssl/ailab.key;\n\
    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;\n\
    add_header X-Content-Type-Options "nosniff" always;\n\
    add_header X-Frame-Options "DENY" always;\n\
    add_header Referrer-Policy "strict-origin-when-cross-origin" always;\n\
    add_header Permissions-Policy "camera=(), microphone=(self), geolocation=()" always;\n\
    location / {\n\
        root   /usr/share/nginx/html;\n\
        index  index.html index.htm;\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    location /taskboard/ {\n\
        proxy_pass http://taskboard:47823/;\n\
        proxy_hide_header X-Frame-Options;\n\
        proxy_hide_header Content-Security-Policy;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Host 127.0.0.1;\n\
        proxy_set_header Origin http://127.0.0.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_read_timeout 3600s;\n\
        proxy_buffering off;\n\
        client_max_body_size 30M;\n\
        add_header X-Frame-Options "SAMEORIGIN" always;\n\
        add_header Content-Security-Policy "frame-ancestors $scheme://$host" always;\n\
        add_header X-Content-Type-Options "nosniff" always;\n\
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;\n\
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
    location = /api/chat/stream {\n\
        proxy_pass http://api:8000/api/chat/stream;\n\
        proxy_read_timeout 600s;\n\
        proxy_send_timeout 600s;\n\
        proxy_buffering off;\n\
        proxy_cache off;\n\
        proxy_request_buffering off;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    }\n\
    location = /api/showroom/ws {\n\
        proxy_pass http://api:8000/api/showroom/ws;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host $host;\n\
        proxy_read_timeout 3600s;\n\
    }\n\
    # B-2-1：443 同样支持官方 Hermes WS 反代（精确路径）\n\
    location = /api/ws {\n\
        proxy_pass http://host.docker.internal:9121;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host 127.0.0.1;\n\
        proxy_set_header Origin http://127.0.0.1;\n\
        proxy_read_timeout 3600s;\n\
        proxy_buffering off;\n\
    }\n\
    location = /api/pty {\n\
        proxy_pass http://host.docker.internal:9121;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host 127.0.0.1;\n\
        proxy_read_timeout 3600s;\n\
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
    location /authen-api/ {\n\
        proxy_pass http://host.docker.internal:8001/;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
    }\n\
    location ^~ /hermes/ { return 404; }\n\
    location ~* \\.(html)$ {\n\
        root   /usr/share/nginx/html;\n\
        add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;\n\
        add_header X-Content-Type-Options "nosniff" always;\n\
        add_header X-Frame-Options "DENY" always;\n\
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;\n\
        add_header Permissions-Policy "camera=(), microphone=(self), geolocation=()" always;\n\
        add_header Cache-Control "no-cache, no-store, must-revalidate";\n\
        add_header Pragma "no-cache";\n\
        add_header Expires 0;\n\
    }\n\
}\n\
server {\n\
    listen 9081 ssl;\n\
    ssl_certificate     /etc/nginx/ssl/ailab.crt;\n\
    ssl_certificate_key /etc/nginx/ssl/ailab.key;\n\
    location / {\n\
        root   /usr/share/nginx/html/web-dashboard;\n\
        index  index.html index.htm;\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
    location /api/ {\n\
        proxy_pass http://host.docker.internal:9121;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host 127.0.0.1;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;\n\
        proxy_set_header X-Forwarded-Proto $scheme;\n\
        proxy_set_header X-Forwarded-Host $host;\n\
        proxy_read_timeout 3600s;\n\
        proxy_buffering off;\n\
    }\n\
}\n' > /etc/nginx/conf.d/default.conf
EXPOSE 80 443 9080 9081
CMD ["nginx", "-g", "daemon off;"]
