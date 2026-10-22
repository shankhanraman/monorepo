# dev: Vite dev server with live reload (docker-compose.yml builds this target)
FROM node:22-alpine AS dev
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
EXPOSE 5176
CMD ["npm","run","dev","--","--host","0.0.0.0","--port","5176"]

# build: static bundle. The browser calls the API same-origin at /api (nginx proxies it), so no CORS.
FROM dev AS build
ARG VITE_API_URL=/api
ENV VITE_API_URL=$VITE_API_URL
RUN npm run build

# prod: what CI publishes (ghcr.io/<owner>/mie-client)
FROM nginx:1.27-alpine AS prod
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
