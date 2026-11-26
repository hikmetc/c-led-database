// A minimal static server that behaves like GitHub Pages: byte-range requests, and
// 404.html (with status 404) for unknown paths.   node scripts/serve-static.mjs <dir> <port>
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';

const root = path.resolve(process.argv[2] ?? 'build');
const port = Number(process.argv[3] ?? 4174);
const TYPES = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.wasm': 'application/wasm', '.svg': 'image/svg+xml', '.png': 'image/png', '.xml': 'application/xml', '.txt': 'text/plain', '.parquet': 'application/octet-stream' };

http
	.createServer((req, res) => {
		let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
		if (process.env.LOG && p.endsWith('.parquet')) console.log(req.method, p, req.headers.range ?? '(no range)');
		let file = path.join(root, p);
		if (!file.startsWith(root)) return res.writeHead(403).end();
		if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
		let status = 200;
		if (!fs.existsSync(file)) {
			file = path.join(root, '404.html');
			status = 404;
		}
		const size = fs.statSync(file).size;
		const headers = { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream', 'accept-ranges': 'bytes' };
		const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range ?? '');
		if (m && status === 200) {
			const start = m[1] === '' ? size - Number(m[2]) : Number(m[1]);
			const end = m[1] !== '' && m[2] !== '' ? Math.min(Number(m[2]), size - 1) : size - 1;
			res.writeHead(206, { ...headers, 'content-range': `bytes ${start}-${end}/${size}`, 'content-length': end - start + 1 });
			return req.method === 'HEAD' ? res.end() : fs.createReadStream(file, { start, end }).pipe(res);
		}
		res.writeHead(status, { ...headers, 'content-length': size });
		req.method === 'HEAD' ? res.end() : fs.createReadStream(file).pipe(res);
	})
	.listen(port, () => console.log(`serving ${root} on http://localhost:${port}/`));
