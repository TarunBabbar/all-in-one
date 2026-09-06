FROM mcr.microsoft.com/playwright:v1.48.0-noble

WORKDIR /app

COPY package.json ./
RUN npm install

COPY worker.js ./

EXPOSE 8787

CMD ["node", "worker.js"]
