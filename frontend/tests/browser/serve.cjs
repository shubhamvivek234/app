// Owned loopback harness bundles real outreach components; tests intercept APIs.
const http = require('http');
const fs = require('fs');
const os = require('os');
const path = require('path');
const webpack = require('webpack');

const output = fs.mkdtempSync(path.join(os.tmpdir(), 'unravler-browser-'));
const compiler = webpack({
  mode: 'production',
  entry: path.join(__dirname, 'entry.jsx'),
  output: { path: output, filename: 'bundle.js' },
  optimization: { minimize: false },
  devtool: false,
  resolve: { extensions: ['.js', '.jsx'] },
  module: { rules: [{ test: /\.jsx?$/, exclude: /node_modules/, use: {
    loader: require.resolve('babel-loader'),
    options: { presets: [[require.resolve('@babel/preset-react'), { runtime: 'automatic' }]] },
  } }] },
});
let server;
const cleanup = () => {
  if (server) server.close();
  compiler.close(() => { fs.rmSync(output, { recursive: true, force: true }); process.exit(); });
};
process.once('SIGTERM', cleanup);
process.once('SIGINT', cleanup);
compiler.run((error, stats) => {
  if (error || stats.hasErrors()) {
    console.error(error || stats.toString({ all: false, errors: true }));
    cleanup();
    process.exitCode = 1;
    return;
  }
  server = http.createServer((request, response) => {
    if (request.url === '/bundle.js') {
      response.writeHead(200, { 'Content-Type': 'text/javascript' });
      fs.createReadStream(path.join(output, 'bundle.js')).pipe(response);
    } else if (new URL(request.url, 'http://127.0.0.1').pathname === '/') {
      response.writeHead(200, { 'Content-Type': 'text/html' });
      response.end('<!doctype html><html><body><div id="root"></div><script src="/bundle.js"></script></body></html>');
    } else {
      response.writeHead(404); response.end();
    }
  }).listen(4179, '127.0.0.1');
});
