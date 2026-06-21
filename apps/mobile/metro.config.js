const { getDefaultConfig } = require('expo/metro-config')
const path = require('path')

const projectRoot = __dirname
const workspaceRoot = path.resolve(projectRoot, '../..')

const config = getDefaultConfig(projectRoot)

// Watch workspace packages (e.g. @reelrecipes/shared)
config.watchFolders = [workspaceRoot]

// Resolve modules from workspace root first, then project root
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, 'node_modules'),
  path.resolve(workspaceRoot, 'node_modules'),
]

// Support TypeScript path aliases
config.resolver.sourceExts = [...config.resolver.sourceExts, 'mjs', 'cjs']

module.exports = config
