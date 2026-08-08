const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

const HTML_DIR = '/tmp/ai_lab_designs/pages';
const DEST_DIR = '/Users/dengzhaoyu/Desktop/AI Lab/frontend/src/pages';
const ASSETS_DIR = '/Users/dengzhaoyu/Desktop/AI Lab/frontend/public/assets';

if (!fs.existsSync(ASSETS_DIR)) {
  fs.mkdirSync(ASSETS_DIR, { recursive: true });
}

// If there were assets, we would copy them. We skip for now since they weren't found.
// But wait, the user said they are in `/tmp/ai_lab_designs/assets`? Let's double check if it exists.
try {
  if (fs.existsSync('/tmp/ai_lab_designs/assets')) {
    execSync(`cp -r /tmp/ai_lab_designs/assets/* "${ASSETS_DIR}"/`);
  }
} catch (e) {}

const files = fs.readdirSync(HTML_DIR).filter(f => f.endsWith('.html'));

files.forEach(file => {
  const content = fs.readFileSync(path.join(HTML_DIR, file), 'utf-8');
  
  // Extract CSS
  const styleMatch = content.match(/<style>([\s\S]*?)<\/style>/);
  const css = styleMatch ? styleMatch[1] : '';
  
  // Extract Body
  const bodyMatch = content.match(/<body>([\s\S]*?)<\/body>/);
  let body = bodyMatch ? bodyMatch[1] : '';
  
  // Remove script tags from body
  body = body.replace(/<script[\s\S]*?<\/script>/gi, '');
  
  // Basic HTML to JSX conversion
  body = body.replace(/class=/g, 'className=');
  body = body.replace(/for=/g, 'htmlFor=');
  body = body.replace(/<!--([\s\S]*?)-->/g, '{/* $1 */}');
  
  // Fix self-closing tags
  body = body.replace(/<(input|img|br|hr|meta|link)([^>]*?)(?<!\/)>/g, '<$1$2 />');
  
  // Style strings to objects (naive)
  body = body.replace(/style="([^"]*)"/g, (match, styleStr) => {
    const rules = styleStr.split(';').filter(r => r.trim());
    const styleObj = {};
    rules.forEach(rule => {
      const [key, val] = rule.split(':');
      if (key && val) {
        const camelKey = key.trim().replace(/-([a-z])/g, g => g[1].toUpperCase());
        styleObj[camelKey] = val.trim();
      }
    });
    return `style={${JSON.stringify(styleObj)}}`;
  });
  
  const baseName = path.basename(file, '.html');
  // map Chinese names to English components
  const nameMap = {
    '登录页': 'Login',
    '需求输入页': 'Dashboard',
    '首页简化方案': 'HomeSimple',
    '加载页': 'Loading',
    '市场洞察专家': 'RoleInsight',
    '开发工程师': 'RoleEngineering',
    '老板': 'RoleFounder',
    '营销经理': 'RoleMarketing',
    '销售经理': 'RoleSales'
  };
  
  const componentName = nameMap[baseName] || baseName;
  
  fs.writeFileSync(path.join(DEST_DIR, `${componentName}.css`), css);
  
  // We write a basic functional component
  const jsx = `import React, { useEffect, useRef } from 'react';
import './${componentName}.css';

export default function ${componentName}() {
  return (
    <>
      ${body}
    </>
  );
}
`;
  
  fs.writeFileSync(path.join(DEST_DIR, `${componentName}.jsx`), jsx);
});
console.log('Conversion complete.');
