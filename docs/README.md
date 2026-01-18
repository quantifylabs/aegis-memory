# Aegis Memory Documentation

Documentation site for Aegis Memory, built with [Mintlify](https://mintlify.com).

## Live Site

- **Docs**: [docs.aegismemory.com](https://docs.aegismemory.com)
- **Home**: [aegismemory.com](https://aegismemory.com)

## Local Development

```bash
npm install -g mintlify
cd docs
mintlify dev
```

Open http://localhost:3000

## Structure

```
docs/
├── mint.json                 # Mintlify configuration
├── introduction/             # Getting started
├── quickstart/               # Installation & first steps
├── guides/                   # In-depth guides
├── integrations/             # Framework docs
├── api-reference/            # SDK & CLI reference
└── tutorials/                # Step-by-step tutorials
```

## Assets Needed

Before deploying, add:

```
/logo/dark.svg      # Logo for dark mode
/logo/light.svg     # Logo for light mode
/favicon.svg        # Browser favicon
```

## DNS Configuration

```
docs.aegismemory.com → cname.mintlify.com
```
