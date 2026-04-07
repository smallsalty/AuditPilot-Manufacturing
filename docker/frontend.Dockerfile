FROM node:20-alpine

WORKDIR /app

COPY apps/frontend /app/apps/frontend
COPY packages/shared-types /app/packages/shared-types

WORKDIR /app/apps/frontend

RUN npm install

EXPOSE 3000

CMD ["npm", "run", "dev", "--", "--hostname", "0.0.0.0", "--port", "3000"]

