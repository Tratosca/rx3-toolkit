const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const nodes=new Map();let completions=0;
function id(name){if(!nodes.has(name))nodes.set(name,{dataset:{},style:{},textContent:'',firstElementChild:{style:{}},setAttribute(k,v){this[k]=v;},removeAttribute(k){delete this[k];}});return nodes.get(name);}
let job={kind:'stems',state:'running',message:'Calcul des waveforms',progress:38,detail:{migration:true,current:'Title',position:1,total:2,trackProgress:76}};
const scope={ask:async()=>job,document:{getElementById:id},t:(key,args)=>key+' '+JSON.stringify(args),window:{i18n:{message:value=>value||'',primary:value=>value||'',number:String},dispatchEvent(){completions++}},clearInterval(){},poll:1,jobDismissed:false,completedJob:"",whenDone:null,CustomEvent:class{},state:{}};
const src=fs.readFileSync('app/ui/web/app.js','utf8');vm.createContext(scope);vm.runInContext(src.slice(src.indexOf('async function readJob()'),src.indexOf('// Wiring')),scope);
(async()=>{
 await scope.readJob();assert.equal(id('job-bar').firstElementChild.style.width,'38%');assert.ok(id('job-detail').textContent.includes('76'));
 scope.jobDismissed=true;await scope.readJob();assert.equal(id('job').hidden,true,'Polling keeps a dismissed job hidden');
 scope.jobDismissed=false;
 job={kind:'stems',state:'done',result:{migrated:2}};
 await scope.readJob();assert.ok(id('job-message').textContent.includes('"count":2'));assert.ok(id('job-diagnostics').textContent.includes('"count":2'));
 const finished=completions;await scope.readJob();assert.equal(completions,finished,'Reopening completed progress does not trigger completion again');
 job={kind:'stems',state:'failed',error:'disk full'};
 await scope.readJob();assert.equal(id('job-message').textContent.split(' ')[0],'job.failed');assert.ok(id('job-diagnostics').textContent.includes('disk full'));
 console.log('Migration UI: track progress, correct completed count and visible failure OK');
})().catch(e=>{console.error(e);process.exitCode=1;});
