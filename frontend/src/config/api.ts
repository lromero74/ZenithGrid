/// <reference types="vite/client" />

/**
 * API Configuration
 *
 * Centralized API URL configuration used across the application.
 * Uses Vite environment variable or defaults to localhost.
 */

export const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8100'
