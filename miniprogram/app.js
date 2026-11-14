App({
  globalData: {baseUrl: 'http://127.0.0.1:8765', cookie: ''},
  onLaunch() { this.globalData.cookie = wx.getStorageSync('session') || ''; },
  request(path, method = 'GET', data) {
    return new Promise((resolve,reject) => wx.request({url: this.globalData.baseUrl+'/api'+path,
      method, data, header: {'Content-Type':'application/json',Cookie:this.globalData.cookie},
      success: r => {
        const cookie = r.header['Set-Cookie'] || r.header['set-cookie'];
        if(cookie){this.globalData.cookie=cookie.split(';')[0];wx.setStorageSync('session',this.globalData.cookie);}
        if(r.statusCode>=200&&r.statusCode<300)resolve(r.data);
        else {if(r.statusCode===401)wx.reLaunch({url:'/pages/login/index'});reject(new Error(typeof r.data.detail==='string'?r.data.detail:'请求失败'));}
      },fail: () => reject(new Error('无法连接 API，请检查本地服务和开发工具域名校验设置'))}));
  }
});
