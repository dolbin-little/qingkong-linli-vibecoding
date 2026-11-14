const labels={pending:'待调度',flying:'配送中',delivered:'已送达',cancelled:'已取消',return_requested:'待回收',returning:'回收返站',returned:'已归还',completed:'已完成'};
Page({data:{orders:[],error:''},onShow(){this.load();this.timer=setInterval(()=>this.load(),5000);},onHide(){clearInterval(this.timer);},onUnload(){clearInterval(this.timer);},
  async load(){try{const s=await getApp().request('/state');this.setData({orders:s.orders.map(o=>({...o,label:labels[o.status]||o.status,productName:s.products[o.product].name,canReturn:o.status==='delivered'&&s.products[o.product].rental&&o.kind==='delivery',canCancel:o.status==='pending'&&o.kind==='delivery',displayAmount:o.settled_amount??o.amount})),error:''});}catch(e){this.setData({error:e.message});}},
  async act(e){try{await getApp().request('/orders/'+e.currentTarget.dataset.id+'/'+e.currentTarget.dataset.action,'POST');this.load();}catch(error){this.setData({error:error.message});}}
});
