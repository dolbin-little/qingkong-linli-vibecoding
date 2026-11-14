Page({data:{username:'resident',password:'',error:'',busy:false},
  input(e){this.setData({[e.currentTarget.dataset.key]:e.detail.value});},
  async login(){if(this.data.busy)return;this.setData({busy:true,error:''});try{await getApp().request('/login','POST',{username:this.data.username,password:this.data.password});wx.redirectTo({url:'/pages/shop/index'});}catch(e){this.setData({error:e.message});}finally{this.setData({busy:false});}}
});
