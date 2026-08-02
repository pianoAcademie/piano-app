FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN rm -rf .next && npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
