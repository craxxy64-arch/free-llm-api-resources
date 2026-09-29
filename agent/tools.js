import fs from "node:fs/promises";
import path from "node:path";
import { exec } from "node:child_process";

const MAX_OUT = 20000;
const clip = (s) => (s.length > MAX_OUT ? s.slice(0, MAX_OUT) + "\n...[truncated]" : s);

export const TOOL_SPECS = {
  list_files: {
    description: "List files recursively in the workspace (or a subfolder).",
    parameters: { type: "object", properties: { dir: { type: "string", description: "Subfolder, default '.'" } } },
  },
  read_file: {
    description: "Read a file. Returns numbered lines.",
    parameters: { type: "object", properties: { path: { type: "string" } }, required: ["path"] },
  },
  search: {
    description: "Search for a text/regex pattern across workspace files. Returns file:line matches.",
    parameters: { type: "object", properties: { pattern: { type: "string" } }, required: ["pattern"] },
  },
  write_file: {
    description: "Create or overwrite a file with full content.",
    parameters: { type: "object", properties: { path: { type: "string" }, content: { type: "string" } }, required: ["path", "content"] },
  },
  edit_file: {
    description: "Replace an exact, unique string in a file. Fails if old_string is missing or ambiguous.",
    parameters: {
      type: "object",
      properties: { path: { type: "string" }, old_string: { type: "string" }, new_string: { type: "string" } },
      required: ["path", "old_string", "new_string"],
    },
  },
  run_command: {
    description: "Run a shell command in the workspace (30s timeout). Use for tests, builds, running code.",
    parameters: { type: "object", properties: { command: { type: "string" } }, required: ["command"] },
  },
};

export function specsFor(names, shellEnabled) {
  return names
    .filter((n) => TOOL_SPECS[n] && (n !== "run_command" || shellEnabled))
    .map((n) => ({ type: "function", function: { name: n, ...TOOL_SPECS[n] } }));
}

function safe(root, p = ".") {
  const full = path.resolve(root, p);
  if (full !== root && !full.startsWith(root + path.sep)) throw new Error("Path escapes workspace");
  return full;
}

async function walk(dir, root, out = []) {
  for (const e of await fs.readdir(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === ".git") continue;
    const full = path.join(dir, e.name);
    if (e.isDirectory()) await walk(full, root, out);
    else out.push(path.relative(root, full));
    if (out.length > 500) break;
  }
  return out;
}

export async function runTool(name, args, root, shellEnabled) {
  try {
    switch (name) {
      case "list_files": {
        const files = await walk(safe(root, args.dir || "."), root);
        return files.join("\n") || "(empty workspace)";
      }
      case "read_file": {
        const text = await fs.readFile(safe(root, args.path), "utf8");
        return clip(text.split("\n").map((l, i) => `${i + 1}\t${l}`).join("\n"));
      }
      case "search": {
        const re = new RegExp(args.pattern, "i");
        const hits = [];
        for (const f of await walk(root, root)) {
          const lines = (await fs.readFile(path.join(root, f), "utf8").catch(() => "")).split("\n");
          lines.forEach((l, i) => re.test(l) && hits.push(`${f}:${i + 1}: ${l.trim()}`));
          if (hits.length > 100) break;
        }
        return hits.join("\n") || "No matches";
      }
      case "write_file": {
        const full = safe(root, args.path);
        await fs.mkdir(path.dirname(full), { recursive: true });
        await fs.writeFile(full, args.content);
        return `Wrote ${args.path} (${args.content.length} chars)`;
      }
      case "edit_file": {
        const full = safe(root, args.path);
        const text = await fs.readFile(full, "utf8");
        const n = text.split(args.old_string).length - 1;
        if (n === 0) return "Error: old_string not found. Re-read the file.";
        if (n > 1) return `Error: old_string matches ${n} places. Add more context.`;
        await fs.writeFile(full, text.replace(args.old_string, () => args.new_string));
        return `Edited ${args.path}`;
      }
      case "run_command": {
        if (!shellEnabled) return "Error: run_command is disabled on this server.";
        return await new Promise((resolve) =>
          exec(args.command, { cwd: root, timeout: 30000, maxBuffer: 1 << 20 }, (err, stdout, stderr) =>
            resolve(clip(`exit=${err ? err.code ?? 1 : 0}\n${stdout}${stderr}`))
          )
        );
      }
      default:
        return `Error: unknown tool ${name}`;
    }
  } catch (e) {
    return `Error: ${e.message}`;
  }
}
