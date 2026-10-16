const js = require('@eslint/js');
const globals = require('globals');

module.exports = [
  { ignores: ['backend/**', 'node_modules/**'] },
  {
    files: ['src/**/*.js', 'test/**/*.js', '*.cjs'],
    languageOptions: { ecmaVersion: 2022, sourceType: 'commonjs', globals: globals.node },
    rules: { ...js.configs.recommended.rules },
  },
  {
    files: ['media/**/*.js'],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'script',
      globals: { ...globals.browser, acquireVsCodeApi: 'readonly' },
    },
    rules: { ...js.configs.recommended.rules },
  },
  {
    files: ['src/**/*.js', 'media/**/*.js', 'test/**/*.js'],
    rules: {
      'no-unused-vars': ['error', { argsIgnorePattern: '^_', caughtErrorsIgnorePattern: '^_' }],
      eqeqeq: ['error', 'always'],
      'no-eval': 'error',
      'no-implied-eval': 'error',
      'no-new-func': 'error',
      'no-restricted-syntax': [
        'error',
        {
          selector: "Property[key.name='shell'][value.value=true]",
          message:
            'Pass an executable and argv with shell:false; never interpolate source content into a shell.',
        },
        {
          selector: 'AssignmentExpression[left.property.name=/^(innerHTML|outerHTML)$/]',
          message:
            'Render untrusted evidence with textContent. Keep HTML construction in the audited static webview shell.',
        },
        {
          selector: "CallExpression[callee.property.name='insertAdjacentHTML']",
          message: 'Use DOM nodes and textContent for evidence.',
        },
      ],
    },
  },
];
