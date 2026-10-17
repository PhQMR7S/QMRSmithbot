export class Api {
  token=''; tenant='';
  async request(path,{method='GET',body,signal}={}){
    const headers={'Accept':'application/json'};
    if(this.token)headers.Authorization=`Bearer ${this.token}`;
    if(this.tenant)headers['X-QMRSmith-Tenant-ID']=this.tenant;
    if(body!==undefined)headers['Content-Type']='application/json';
    const response=await fetch(`/api/v1${path}`,{method,headers,body:body===undefined?undefined:JSON.stringify(body),signal,credentials:'same-origin',cache:'no-store'});
    const data=response.status===204?null:await response.json().catch(()=>null);
    if(!response.ok){const error=new Error(typeof data?.detail==='string'?data.detail:`HTTP ${response.status}`);error.status=response.status;error.requestId=response.headers.get('X-Request-ID');throw error;}
    return data;
  }
}
