import re

with open('src/pages/CreatePostForm.js', 'r') as f:
    content = f.read()

# We want to replace everything from " {/* Account Selection */}" to "         {/* Right Sidebar */}"
# But we'll do it using regex to be safe.

start_marker = "            {/* Account Selection */}"
end_marker = "          {/* Right Sidebar */}"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker)


instagram_ui = """            {/* Instagram Composer Area */}
            <div className="bg-white rounded-lg border border-gray-200 p-6 mb-4">
              
              {/* Account Avatars & Platform Icons Header */}
              <div className="flex items-center gap-4 mb-6">
                <div className="flex -space-x-2">
                   {availableAccounts
                    .filter(a => selectedAccounts.includes(a.id))
                    .map((account) => {
                    const platformInfo = platformIcons[account.platform] || {};
                    const Icon = platformInfo.icon || FaFacebook;
                    return (
                      <div key={account.id} className="relative">
                        {account.picture_url ? (
                          <img
                            src={account.picture_url}
                            alt={account.platform_username}
                            className="w-10 h-10 rounded-full object-cover border-2 border-white shadow-sm"
                          />
                        ) : (
                          <div className={`w-10 h-10 rounded-full ${getAvatarColor(account.platform_username)} flex items-center justify-center text-white text-sm font-medium border-2 border-white shadow-sm`}>
                            {account.platform_username?.charAt(0)?.toUpperCase() || 'U'}
                          </div>
                        )}
                        <div className="absolute -bottom-1 -right-1 w-4 h-4 rounded-full bg-white border border-gray-100 flex items-center justify-center shadow-sm">
                          <Icon className={`text-[10px] ${platformInfo.color}`} />
                        </div>
                      </div>
                    );
                  })}
                  {selectedAccounts.length === 0 && (
                    <div className="w-10 h-10 rounded-full bg-gray-100 border-2 border-dashed border-gray-300 flex items-center justify-center text-gray-400">
                      ?
                    </div>
                  )}
                </div>
              </div>

              {type === 'video' && getSelectedPlatforms().includes('instagram') ? (
                // INSTAGRAM SPECIFIC UI
                <>
                  {/* Post Type Selection */}
                  <div className="flex items-center gap-6 mb-6">
                    <FaInstagram className="text-pink-500 text-xl" />
                    <div className="flex items-center gap-4">
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input 
                          type="radio" 
                          name="postFormat" 
                          value="Post" 
                          checked={postFormat === 'Post'} 
                          onChange={(e) => setPostFormat(e.target.value)}
                          className="text-pink-500 focus:ring-pink-500 w-4 h-4" 
                        />
                        <span className="text-sm font-medium text-gray-900">Post</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input 
                          type="radio" 
                          name="postFormat" 
                          value="Reel" 
                          checked={postFormat === 'Reel'} 
                          onChange={(e) => setPostFormat(e.target.value)}
                          className="text-pink-500 focus:ring-pink-500 w-4 h-4" 
                        />
                        <span className="text-sm font-medium text-gray-900">Reel</span>
                      </label>
                      <label className="flex items-center gap-2 cursor-pointer">
                        <input 
                          type="radio" 
                          name="postFormat" 
                          value="Story" 
                          checked={postFormat === 'Story'} 
                          onChange={(e) => setPostFormat(e.target.value)}
                          className="text-pink-500 focus:ring-pink-500 w-4 h-4" 
                        />
                        <span className="text-sm font-medium text-gray-900">Story</span>
                      </label>
                    </div>
                  </div>

                  {/* Caption Textarea */}
                  <Textarea
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder="What would you like to share?"
                    rows={1}
                    className="resize-none bg-transparent border-none focus-visible:ring-0 px-0 text-base placeholder:text-gray-400 min-h-[40px] mb-4"
                  />

                  {/* Inline Media Upload (only show if no media uploaded) */}
                  {!uploadedMedia && (
                    <div
                      className="border border-dashed border-gray-300 rounded-lg p-8 mb-6 bg-transparent transition-colors hover:border-gray-400 hover:bg-gray-50 cursor-pointer flex flex-col items-center justify-center min-h-[200px] max-w-sm"
                      onClick={(e) => {
                        if (!uploading && !uploadedMedia) {
                          fileInputRef.current?.click();
                        }
                      }}
                      onDrop={handleDrop}
                      onDragOver={handleDragOver}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept={type === 'video' ? 'video/*' : type === 'image' ? 'image/*' : 'image/*,video/*'}
                        onChange={handleFileUpload}
                        className="hidden"
                      />
                      <input
                        ref={coverImageInputRef}
                        type="file"
                        accept="image/*"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                             if (type === 'video' && mediaRawAspectRatio) {
                               const reader = new FileReader();
                               reader.addEventListener('load', () => {
                                 setCropImageSrc(reader.result);
                                 setShowCropper(true);
                               });
                               reader.readAsDataURL(file);
                             } else {
                               uploadCoverImageToBackend(file);
                             }
                             e.target.value = null;
                          }
                        }}
                        className="hidden"
                      />

                      {uploading ? (
                        <div className="flex flex-col items-center">
                          <p className="text-gray-900 font-medium mb-2 text-sm">Uploading...</p>
                          <div className="w-48 bg-gray-200 rounded-full h-1.5 mb-1 relative overflow-hidden">
                            <div
                              className="bg-gray-800 h-1.5 rounded-full transition-all duration-300"
                              style={{ width: `${uploadProgress}%` }}
                            ></div>
                          </div>
                        </div>
                      ) : (
                        <>
                          <div className="w-10 h-10 rounded flex items-center justify-center mb-3 text-gray-400 group-hover:text-gray-500 transition-colors">
                            <FaImage className="text-2xl" />
                          </div>
                          <p className="text-gray-900 font-medium text-sm text-center">Drag & drop or<br/><span className="text-blue-600 font-normal">select a file</span></p>
                        </>
                      )}
                    </div>
                  )}
                  {uploadedMedia && (
                     // Hidden inputs still needed when media is uploaded so cover image can be triggered from right sidebar
                     <div className="hidden">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept={type === 'video' ? 'video/*' : type === 'image' ? 'image/*' : 'image/*,video/*'}
                        onChange={handleFileUpload}
                      />
                      <input
                        ref={coverImageInputRef}
                        type="file"
                        accept="image/*"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) {
                             if (type === 'video' && mediaRawAspectRatio) {
                               const reader = new FileReader();
                               reader.addEventListener('load', () => {
                                 setCropImageSrc(reader.result);
                                 setShowCropper(true);
                               });
                               reader.readAsDataURL(file);
                             } else {
                               uploadCoverImageToBackend(file);
                             }
                             e.target.value = null;
                          }
                        }}
                      />
                     </div>
                  )}

                  {/* Actions Toolbar */}
                  <div className="flex items-center justify-between border-y border-gray-100 py-3 mb-6">
                    <div className="flex items-center gap-4">
                      <button className="w-6 h-6 rounded-full bg-slate-900 text-white flex items-center justify-center text-xs font-bold font-serif italic hover:opacity-80 transition-opacity">
                        C
                      </button>
                      <button className="text-gray-500 hover:text-gray-700 transition-colors">
                        <FaSmile className="text-lg" />
                      </button>
                      <button className="text-gray-500 hover:text-gray-700 transition-colors">
                        <FaClipboardList className="text-lg" />
                      </button>
                    </div>
                    <span className="text-xs text-gray-400 font-medium bg-gray-50 px-2 py-1 rounded">
                      {2200 - content.length}
                    </span>
                  </div>

                  {/* Advanced Inputs */}
                  <div className="space-y-4 max-w-2xl">
                    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
                      <Label className="text-sm font-semibold text-gray-900">Add Stickers</Label>
                      <div className="flex items-center gap-2">
                        <Button variant="outline" size="sm" className="h-8 rounded-full px-4 text-xs font-medium border-gray-300 text-gray-700">
                          <FaMusic className="mr-2 text-gray-400" /> Music
                        </Button>
                        <Button variant="outline" size="sm" className="h-8 rounded-full px-4 text-xs font-medium border-gray-300 text-gray-700">
                          <FaShoppingBag className="mr-2 text-gray-400" /> Tag Products
                        </Button>
                        <div className="ml-auto text-blue-600 text-sm font-medium flex items-center gap-1 cursor-pointer">
                          <span className="text-xl leading-none -mt-1">⚙</span> Automatic <FaChevronDown className="text-[10px]" />
                        </div>
                      </div>
                    </div>

                    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
                      <Label className="text-sm font-semibold text-gray-900">First Comment</Label>
                      <Input 
                        placeholder="Your comment" 
                        value={firstComment}
                        onChange={(e) => setFirstComment(e.target.value)}
                        className="bg-white border-gray-200" 
                      />
                    </div>

                    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
                      <Label className="text-sm font-semibold text-gray-900">Location</Label>
                      <div className="relative">
                        <Input 
                          placeholder="Type the location" 
                          value={location}
                          onChange={(e) => setLocation(e.target.value)}
                          className="bg-white border-gray-200" 
                        />
                        <FaChevronDown className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs pointer-events-none" />
                      </div>
                    </div>

                    <div className="grid grid-cols-[120px_1fr] items-center gap-4">
                      <div className="flex items-center gap-1">
                        <Label className="text-sm font-semibold text-gray-900">Shop Grid Link</Label>
                        <FaInfoCircle className="text-gray-400 text-xs" />
                      </div>
                      <Input 
                        placeholder="Website or Product URL" 
                        value={shopGridLink}
                        onChange={(e) => setShopGridLink(e.target.value)}
                        className="bg-white border-gray-200" 
                      />
                    </div>
                  </div>
                </>
              ) : (
                // GENERIC UI for non-video or non-instagram posts
                <div className="p-8 text-center border-2 border-dashed border-gray-200 rounded-lg text-gray-500">
                    <p>Select an Instagram account to see the Composer.</p>
                    <p className="text-sm mt-2">Currently, only the Instagram Video/Reel composer interface is fully customized.</p>
                </div>
              )}
            </div>
"""

modified_content = content[:start_idx] + instagram_ui + "\\n" + content[end_idx:]

with open('src/pages/CreatePostForm.js', 'w') as f:
    f.write(modified_content)

print('Patched UI section')

