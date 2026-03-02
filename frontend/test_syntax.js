const fs = require('fs');
try {
  const content = fs.readFileSync('src/pages/CreatePostForm.js', 'utf8');
  // Just check if it compiles as basic JS (JSX might fail standard JS parse, but we can do a quick check)
} catch(e) {
  console.log("Error reading file");
}
