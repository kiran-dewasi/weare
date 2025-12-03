// API Configuration
export const API_CONFIG = {
    BASE_URL: "http://127.0.0.1:8001",
    API_KEY: "k24-secret-key-123",

    // Helper to get headers
    getHeaders: () => ({
        "Content-Type": "application/json",
        "x-api-key": API_CONFIG.API_KEY
    })
};
