// Development Logger
// Only logs in development mode, silent in production

const isDev = process.env.NODE_ENV === 'development';

export const logger = {
  log: (...args) => {
    if (isDev) console.log(...args);
  },
  
  error: (...args) => {
    if (isDev) console.error(...args);
  },
  
  warn: (...args) => {
    if (isDev) console.warn(...args);
  },
  
  info: (...args) => {
    if (isDev) console.info(...args);
  },
  
  debug: (...args) => {
    if (isDev) console.debug(...args);
  },
};

export default logger;
