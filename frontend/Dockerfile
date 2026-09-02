FROM node:22-alpine AS build
WORKDIR /src
COPY package.json package-lock.json tsconfig.json next-env.d.ts next.config.ts ./
COPY app ./app
ARG NEXT_PUBLIC_API_URL=/api
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL
RUN npm ci --no-audit --no-fund && npm run build
FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production
COPY --from=build /src/.next/standalone ./
COPY --from=build /src/.next/static ./.next/static
USER node
EXPOSE 3000
CMD ["node", "server.js"]
