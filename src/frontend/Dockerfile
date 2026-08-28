# BuildingAssist frontend — nginx serving the pre-built Vite/TypeScript bundle.
# The bundle is produced on the host with npm through the configured package
# proxy and copied in here, so the ACR image build needs no registry access.
# The backend URL is injected at container start from the BACKEND_URL env var.
FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY dist /usr/share/nginx/html

# nginx:alpine runs every executable script in /docker-entrypoint.d before starting.
COPY docker-entrypoint.sh /docker-entrypoint.d/40-buildingassist-config.sh
RUN chmod +x /docker-entrypoint.d/40-buildingassist-config.sh

EXPOSE 80
