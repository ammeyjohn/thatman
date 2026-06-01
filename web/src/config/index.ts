export interface AppConfig {
  API_BASE_URL: string;
  API_TIMEOUT: number;
  ENABLE_MOCK: boolean;
}

declare global {
  interface Window {
    APP_CONFIG?: AppConfig;
  }
}

const getEnvVar = (key: string, defaultValue: string): string => {
  if (typeof import.meta.env !== 'undefined') {
    return import.meta.env[key] || defaultValue;
  }
  return defaultValue;
};

export const config: AppConfig = {
  API_BASE_URL: getEnvVar('VITE_API_BASE_URL', 'http://localhost:7778/v1'),
  API_TIMEOUT: parseInt(getEnvVar('VITE_API_TIMEOUT', '30000'), 10),
  ENABLE_MOCK: getEnvVar('VITE_ENABLE_MOCK', 'false') === 'true',
};

export const getConfig = (): AppConfig => {
  if (typeof window !== 'undefined' && window.APP_CONFIG) {
    return window.APP_CONFIG;
  }
  return config;
};

export default config;
