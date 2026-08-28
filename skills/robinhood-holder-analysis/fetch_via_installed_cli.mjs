#!/usr/bin/env node
/**
 * 用本机已装的 gmgn-cli OpenAPI 客户端拉 robinhood 数据。
 * 1.1.x 的 CLI 会在本地拒认 chain=robinhood，但服务端已经支持。
 *
 * 用法:
 *   node fetch_via_installed_cli.mjs info <address>
 *   node fetch_via_installed_cli.mjs holders <address> [limit]
 */
import { execSync } from "child_process";
import { realpathSync } from "fs";
import { dirname, join } from "path";
import { pathToFileURL } from "url";

function cliPkgRoot() {
  const bin = execSync("which gmgn-cli", { encoding: "utf8" }).trim();
  return join(dirname(realpathSync(bin)), "..");
}

async function loadUndici(pkgRoot) {
  const undiciUrl = pathToFileURL(join(pkgRoot, "node_modules/undici/index.js")).href;
  return import(undiciUrl);
}

async function setupProxy(pkgRoot) {
  const { setGlobalDispatcher, ProxyAgent, Agent, buildConnector } = await loadUndici(pkgRoot);
  const proxy =
    process.env.HTTPS_PROXY ??
    process.env.https_proxy ??
    process.env.HTTP_PROXY ??
    process.env.http_proxy;
  if (proxy) {
    setGlobalDispatcher(new ProxyAgent(proxy));
  } else {
    const connector = buildConnector({ family: 4 });
    setGlobalDispatcher(new Agent({ connect: connector }));
  }
}

async function main() {
  const [cmd, address, limit] = process.argv.slice(2);
  if (!cmd || !address) {
    console.error("usage: fetch_via_installed_cli.mjs <info|holders> <address> [limit]");
    process.exit(2);
  }
  const pkgRoot = cliPkgRoot();
  await setupProxy(pkgRoot);
  const { OpenApiClient } = await import(
    pathToFileURL(join(pkgRoot, "dist/client/OpenApiClient.js")).href
  );
  const { getConfig } = await import(pathToFileURL(join(pkgRoot, "dist/config.js")).href);
  const client = new OpenApiClient(getConfig());
  const chain = "robinhood";
  let data;
  if (cmd === "info") {
    data = await client.getTokenInfo(chain, address);
  } else if (cmd === "holders") {
    data = await client.getTokenTopHolders(chain, address, {
      limit: limit || "100",
    });
  } else {
    console.error(`unknown cmd: ${cmd}`);
    process.exit(2);
  }
  process.stdout.write(JSON.stringify(data));
}

main().catch((err) => {
  console.error(String(err?.message || err));
  process.exit(1);
});
