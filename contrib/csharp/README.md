# C# Roslyn Graph Emitter

This folder contains a small C# console utility that emits dependency graph edges for Desloppify.
It is optional helper tooling (not part of the core Python package/runtime).

## Project

- `RoslynGraphEmitter/` - regular .NET console app (no `dotnet-script`).

## Run manually

From repository root:

```bash
dotnet run --project contrib/csharp/RoslynGraphEmitter/RoslynGraphEmitter.csproj -- .
```

Output format:

```json
{"edges":[{"source":"...","target":"..."}]}
```

## Use with Desloppify

```bash
desloppify --lang csharp detect deps --path . \
  --lang-opt "roslyn_cmd=dotnet run --project contrib/csharp/RoslynGraphEmitter/RoslynGraphEmitter.csproj -- {path}"
```

```bash
desloppify --lang csharp scan --path . \
  --lang-opt "roslyn_cmd=dotnet run --project contrib/csharp/RoslynGraphEmitter/RoslynGraphEmitter.csproj -- {path}"
```

If the Roslyn command fails, Desloppify automatically falls back to heuristic graphing.
