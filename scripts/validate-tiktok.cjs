// Offline behavior checks, with stubbed imports and no TikTok/API credentials.
const fs = require('fs');
const path = require('path');
const vm = require('vm');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const ts = require(process.env.TYPESCRIPT_PATH || require.resolve('typescript', { paths: [path.join(root, 'postiz')] }));
const files = [
  'postiz/libraries/nestjs-libraries/src/integrations/social/tiktok.provider.ts',
  'postiz/apps/backend/src/api/routes/integrations.controller.ts',
  'postiz/apps/backend/src/public-api/routes/v1/public.integrations.controller.ts',
  'postiz/apps/frontend/src/components/launches/calendar.context.tsx',
  'postiz/apps/frontend/src/components/new-launch/providers/tiktok/tiktok.provider.tsx',
];
let providerOutput;
for (const file of files) {
  const output = ts.transpileModule(fs.readFileSync(path.join(root,file),'utf8'), {
    fileName:file, reportDiagnostics:true,
    compilerOptions:{target:ts.ScriptTarget.ES2022,module:ts.ModuleKind.CommonJS,
      experimentalDecorators:true,jsx:ts.JsxEmit.ReactJSX},
  });
  assert.equal((output.diagnostics || []).filter(x=>x.category===ts.DiagnosticCategory.Error).length,0,file);
  if (!providerOutput) providerOutput=output.outputText;
}
class SocialAbstract {
  checkScopes(wanted, actual) { for(const s of wanted) assert.ok(actual.split(',').includes(s)); }
  assetBoolean(value) { return value === true; }
}
const fakeEnv={TIKTOK_UPLOAD_ONLY:'true',TIKTOK_CLIENT_ID:'test-key',TIKTOK_CLIENT_SECRET:'test-secret',FRONTEND_URL:'https://example.test'};
let fetchCalls=[];
const fakeDay=()=>({add:()=>({unix:()=>86400}),unix:()=>0});
const context={exports:{},process:{env:fakeEnv},Buffer,URLSearchParams,
  require(name){
    if(name==='dayjs')return {default:fakeDay};
    if(name.endsWith('social.abstract'))return {SocialAbstract,BadBody:class extends Error {},Disconnect:class extends Error {},RefreshToken:class extends Error {}};
    if(name.endsWith('rules.description.decorator'))return {Rules:()=>klass=>klass};
    if(name.endsWith('make.secure.id'))return {makeSecureId:()=> 'test-state'};
    if(name.endsWith('has.extension'))return {hasExtension:(p,e)=>p.endsWith('.'+e)};
    return {};
  },
  async fetch(url,options){
    fetchCalls.push({url,options});
    return {json:async()=>url.includes('/oauth/token/')
      ? {access_token:'test-token',refresh_token:'refresh',scope:'user.info.basic,video.upload'}
      : {data:{user:{open_id:'test-user',avatar_url:'https://example.test/avatar',display_name:'Test'}}}};
  },
};
vm.runInNewContext(providerOutput,context);
const provider=new context.exports.TiktokProvider();
const video={message:'Caption to copy',settings:{content_posting_method:'DIRECT_POST'},media:[{path:'https://example.test/clip.mp4'}]};
(async()=>{
  assert.deepEqual(Array.from(provider.scopes),['user.info.basic','video.upload']);
  const auth=await provider.generateAuthUrl();
  assert.equal(new URL(auth.url).searchParams.get('scope'),'user.info.basic,video.upload');
  assert.equal(provider.contentPostingMethod(video),'UPLOAD');
  assert.equal(provider.postingMethod(provider.contentPostingMethod(video),false),'/inbox/video/init/');
  assert.equal(JSON.stringify(provider.buildTikokPostInfoBody(video)),'{}');
  const user=await provider.authenticate({code:'test',codeVerifier:'test'});
  assert.equal(user.name,'Test');assert.equal(user.username,'');
  assert.equal(new URL(fetchCalls[1].url).searchParams.get('fields'),'open_id,avatar_url,display_name');
  fetchCalls=[];await provider.refreshToken('refresh');
  assert.equal(new URL(fetchCalls[1].url).searchParams.get('fields'),'open_id,avatar_url,display_name');
  fetchCalls=[];await provider.maxVideoLength('test');assert.equal(fetchCalls.length,0);
  fakeEnv.TIKTOK_UPLOAD_ONLY='false';
  assert.ok(provider.scopes.includes('video.publish'));
  assert.equal(provider.contentPostingMethod(video),'DIRECT_POST');
  assert.equal(provider.buildTikokPostInfoBody(video).post_info.title,'Caption to copy');
  console.log('TypeScript syntax (5 files) and TikTok upload-only behavior: OK');
})().catch(e=>{console.error(e);process.exitCode=1});
