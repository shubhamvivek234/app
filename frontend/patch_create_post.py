import re

with open('src/pages/CreatePostForm.js', 'r') as f:
    content = f.read()

# Make imports for the new UI components we'll need
imports_to_add = """
import {
  FaSmile,
  FaClipboardList,
  FaMusic,
  FaShoppingBag,
  FaMapMarkerAlt,
  FaLink,
} from 'react-icons/fa';
"""

# The start of the return statement
return_index = content.find("  return (\\n    <DashboardLayout>")

# We will reconstruct the component
# We need to add state for the new Instagram fields right before the return
instagram_state = """
  // Instagram specific state
  const [postFormat, setPostFormat] = useState('Post'); // Post, Reel, Story
  const [firstComment, setFirstComment] = useState('');
  const [location, setLocation] = useState('');
  const [shopGridLink, setShopGridLink] = useState('');
"""

modified_content = content[:return_index] + instagram_state + "\\n" + content[return_index:]

# Update the imports
import_insert_index = modified_content.find("import {\\n  FaTwitter,")
modified_content = modified_content[:import_insert_index] + imports_to_add + modified_content[import_insert_index:]


with open('src/pages/CreatePostForm.js', 'w') as f:
    f.write(modified_content)

print('Patched state and imports')

