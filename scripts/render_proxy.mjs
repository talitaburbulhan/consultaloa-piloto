import http from "node:http";

const publicPort = Number(process.env.PORT || 10000);
const apiSocket = process.env.API_SOCKET || "/tmp/consulta-loa-api.sock";

function upstreamFor(request) {
  if (request.url?.startsWith("/api")) {
    return { socketPath: apiSocket };
  }
  return { host: "127.0.0.1", port: 3000 };
}

const server = http.createServer((request, response) => {
  const upstream = http.request(
    {
      ...upstreamFor(request),
      method: request.method,
      path: request.url,
      headers: request.headers,
    },
    (upstreamResponse) => {
      response.writeHead(upstreamResponse.statusCode ?? 502, upstreamResponse.headers);
      upstreamResponse.pipe(response);
    },
  );

  upstream.on("error", (error) => {
    if (!response.headersSent) {
      response.writeHead(502, { "content-type": "application/json; charset=utf-8" });
    }
    response.end(JSON.stringify({ detail: "Serviço temporariamente indisponível." }));
    console.error("Falha ao encaminhar solicitação:", error.message);
  });
  request.pipe(upstream);
});

server.listen(publicPort, "0.0.0.0", () => {
  console.log(`Servidor público do piloto disponível na porta ${publicPort}`);
});
