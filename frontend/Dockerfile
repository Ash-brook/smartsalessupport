# Frontend image: runs the Vite dev server. Build context is ./frontend.
FROM node:20-slim

WORKDIR /app

COPY package*.json ./
RUN npm install

COPY . .

EXPOSE 5173

# --host makes Vite listen on 0.0.0.0 so the port is reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host"]
