# Step 1: Build the React app using Node.js
FROM node:16 AS build

# Set the working directory inside the container
WORKDIR /app

# Copy package.json and package-lock.json to install dependencies
COPY package*.json ./

# Install dependencies
RUN npm install

# Copy all files from your local machine to the working directory in the container
COPY . .

# Build the React app (this will create a 'build' folder with production-ready files)
RUN npm run build

# Step 2: Serve the React app using Nginx
FROM nginx:alpine

# Copy the build folder from the previous step into Nginx's HTML directory
COPY --from=build /app/build /usr/share/nginx/html


# Run Nginx to serve the React app
CMD ["nginx", "-g", "daemon off;"]
