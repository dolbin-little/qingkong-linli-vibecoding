Page({
  data:{products:[],selected:null,pickupPoints:[],pickupIndex:0,pickupId:'',pickupName:'',quantity:1,busy:false,error:''},
  onShow(){this.load();},
  async load(){
    try{
      const s=await getApp().request('/state');
      const points=(s.pickup_points||[]).map(p=>({...p,label:p.name+(p.available?'':'（禁飞区内，暂不可选）')}));
      const index=points.findIndex(p=>p.id===this.data.pickupId&&p.available);
      this.setData({products:Object.entries(s.products).map(([id,p])=>({...p,id,stock:s.stations.filter(st=>st.online).reduce((n,st)=>n+st.inventory[id],0)})),
        pickupPoints:points,pickupIndex:Math.max(index,0),pickupId:index>=0?points[index].id:'',pickupName:index>=0?points[index].name:'',error:''});
    }catch(e){this.setData({error:e.message});}
  },
  choose(e){this.setData({selected:this.data.products.find(p=>p.id===e.currentTarget.dataset.id),error:''});},
  input(e){this.setData({quantity:e.detail.value});},
  choosePickup(e){
    const index=Number(e.detail.value),p=this.data.pickupPoints[index];
    if(!p||!p.available){this.setData({pickupId:'',pickupName:'',error:'该取件点暂不可用，请选择其他取件点。'});return;}
    this.setData({pickupIndex:index,pickupId:p.id,pickupName:p.name,error:''});
  },
  async submit(){
    if(this.data.busy||!this.data.selected)return;
    if(!this.data.pickupId){this.setData({error:'请先选择公共取件点。'});return;}
    const quantity=Number(this.data.quantity);
    if(!Number.isInteger(quantity)||quantity<1||quantity>3){this.setData({error:'数量请输入 1 至 3 的整数。'});return;}
    this.setData({busy:true,error:''});
    try{
      await getApp().request('/orders','POST',{product:this.data.selected.id,quantity,pickup_point_id:this.data.pickupId,priority:1,deadline_minutes:6});
      this.setData({selected:null});wx.navigateTo({url:'/pages/orders/index'});
    }catch(e){this.setData({error:e.message});}finally{this.setData({busy:false});}
  },
  orders(){wx.navigateTo({url:'/pages/orders/index'});}
});
