import { defineConfig, loadEnv, transformWithOxc } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'url';

/**
 * Custom plugin to handle JSX in .js files.
 * CRA allowed JSX in plain .js files, but Vite 8 (rolldown/OXC) only processes
 * JSX in .jsx/.tsx by default. This plugin pre-transforms .js files that contain
 * JSX before rolldown's native transform plugin processes them.
 */
function jsFilesWithJSX() {
  return {
    name: 'js-files-jsx',
    enforce: 'pre',
    async transform(code, id) {
      // Only handle .js files (not node_modules, not .jsx/.tsx already handled)
      if (!id.endsWith('.js') || id.includes('node_modules')) return null;
      // Only transform if the file looks like it contains JSX
      if (!code.includes('<') && !code.includes('React')) return null;
      try {
        const result = await transformWithOxc(code, id, {
          lang: 'jsx',
          jsx: { runtime: 'automatic' },
        });
        return { code: result.code, map: result.map };
      } catch {
        // Not JSX, return unchanged
        return null;
      }
    },
  };
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '');
  const backendUrl = env.REACT_APP_BACKEND_URL || 'http://localhost:8001';

  return {
    plugins: [
      jsFilesWithJSX(),
      react(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      port: 3000,
      proxy: {
        '/api': {
          target: backendUrl,
          changeOrigin: true,
          secure: false,
        },
        '/uploads': {
          target: backendUrl,
          changeOrigin: true,
          secure: false,
        },
      },
    },
    optimizeDeps: {
      // During dependency pre-bundling, rolldown is used (Vite 8+).
      // Tell it to parse .js files as jsx so files like index.js don't break the scan.
      rolldownOptions: {
        moduleTypes: { '.js': 'jsx' },
      },
    },

    build: {
      outDir: 'build',
      sourcemap: false,
      rollupOptions: {
        // Tell rolldown to parse .js files as JSX so the bundler accepts them
        moduleTypes: {
          '.js': 'jsx',
        },
        output: {
          manualChunks(id) {
            if (
              id.includes('node_modules/react/') ||
              id.includes('node_modules/react-dom/') ||
              id.includes('node_modules/react-router-dom/')
            ) {
              return 'vendor';
            }
            if (id.includes('node_modules/recharts/')) {
              return 'charts';
            }
            if (id.includes('node_modules/react-icons/')) {
              return 'icons';
            }
          },
        },
      },
    },
    // Support both REACT_APP_ and VITE_ prefixed env vars
    envPrefix: ['REACT_APP_', 'VITE_'],
    define: {
      // Polyfill process.env.NODE_ENV for libraries that use it
      'process.env.NODE_ENV': JSON.stringify(mode),
      // Backwards compat: expose all REACT_APP_* vars as process.env.REACT_APP_*
      // so existing source code doesn't need to change.
      ...Object.fromEntries(
        Object.entries(env)
          .filter(([key]) => key.startsWith('REACT_APP_'))
          .map(([key, val]) => [`process.env.${key}`, JSON.stringify(val)])
      ),
    },
    test: {
      globals: true,
      environment: 'jsdom',
      setupFiles: './src/setupTests.js',
    },
  };
});
