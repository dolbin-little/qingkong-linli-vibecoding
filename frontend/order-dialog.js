'use strict';

function newOrder(product='powerbank') {
  const points=S.pickup_points||[];
  const initial=page==='map'?selectedPoint:null;
  let destination=null;
  const blocked=(x,y)=>S.zones.some(z=>x>=z.x&&x<=z.x+z.w&&y>=z.y&&y<=z.y+z.h);
  const matching=(x,y)=>points.find(p=>p.x===x&&p.y===y);
  modal('创建即时配送订单', `<form id="order-form">
    <div class="notice">选择取件点即可下单，地址和位置自动关联。支付为模拟操作，不产生真实扣款。</div>
    <div class="form-grid">
      <label>配送物品<select name="product">${Object.entries(S.products).map(([id,v])=>`<option value="${id}" ${id===product?'selected':''}>${esc(v.name)} · ¥${v.price}${esc(v.unit.replace('元',''))}</option>`).join('')}</select></label>
      <label>数量<input type="number" name="quantity" min="1" max="3" value="1" required></label>
      <label class="span-2">公共取件点<select id="pickup-select" aria-describedby="pickup-summary" required>
        <option value="" disabled selected>请选择附近公共取件点</option>
        ${points.map(p=>`<option value="${esc(p.id)}" ${p.available?'':'disabled'}>${esc(p.name)}${p.available?'':'（禁飞区内，暂不可选）'}</option>`).join('')}
        <option value="custom">其他位置 · 在下方地图选择</option>
      </select></label>
    </div>
    <p id="pickup-summary" class="pickup-summary" role="status">请选择取件点，或展开地图选择位置。</p>
    <details id="pickup-map-panel" class="pickup-map-panel"><summary>在地图上选择取件位置</summary>
      <p class="route-details">点击蓝色标记选择公共取件点，或点击空白处选择其他位置。斜纹区域禁止取件。</p>
      <div id="pickup-map-host"></div>
    </details>
    ${admin()?'<details class="pickup-debug"><summary>查看位置坐标（管理员）</summary><p id="pickup-coordinates" class="route-details">尚未选择位置</p></details>':''}
    <p id="pickup-error" class="error" role="alert"></p>
    <div class="form-grid">
      <label>任务优先级<select name="priority"><option value="1">普通需求</option><option value="2">优先配送</option><option value="3">紧急需求</option></select></label>
      <label>送达时间窗<select name="deadline_minutes"><option value="6">6 分钟内</option><option value="3">3 分钟内</option><option value="15">15 分钟内</option></select></label>
    </div>
    <div class="form-actions"><button type="button" class="btn" data-close>取消</button><button id="submit-order" class="btn primary" type="submit" disabled>确认模拟支付并下单</button></div>
  </form>`);
  const form=$('#order-form'),select=$('#pickup-select'),submit=$('#submit-order');
  function drawMap(){
    $('#pickup-map-host').innerHTML=renderMap(true,{id:'order-map',point:destination?[destination.x,destination.y]:null,zoom:1,pickups:true});
    $('#order-map').onclick=e=>{
      const marker=e.target.closest('[data-pickup]');
      if(marker){const p=points.find(p=>p.id===marker.dataset.pickup);if(p)choose(p.x,p.y);return;}
      const svg=e.currentTarget,point=svg.createSVGPoint();point.x=e.clientX;point.y=e.clientY;
      const coords=point.matrixTransform(svg.getScreenCTM().inverse());
      choose(Math.round(coords.x),Math.round(coords.y));
    };
  }
  function choose(x,y){
    if(x<20||x>980||y<20||y>680||blocked(x,y)){
      destination=null;select.value='custom';submit.disabled=true;
      $('#pickup-summary').textContent='所选位置不可用，请重新选择取件点。';
      $('#pickup-error').textContent='请选择地图边界内、禁飞区外的位置。';
      if($('#pickup-coordinates'))$('#pickup-coordinates').textContent='尚未选择有效位置';
      drawMap();return;
    }
    const preset=matching(x,y);
    destination={id:preset?.id,x,y,name:preset?.name||`地图取件点（${x}, ${y}）`};
    select.value=preset?preset.id:'custom';
    $('#pickup-summary').textContent='取件位置：'+destination.name+'。地址与地图位置已关联。';
    $('#pickup-error').textContent='';submit.disabled=false;
    if($('#pickup-coordinates'))$('#pickup-coordinates').textContent=`X：${x} 米，Y：${y} 米（自动关联，无需填写）`;
    drawMap();
  }
  select.onchange=()=>{
    const preset=points.find(p=>p.id===select.value);
    if(preset)choose(preset.x,preset.y);
    else{
      destination=null;submit.disabled=true;$('#pickup-map-panel').open=true;
      $('#pickup-summary').textContent='请在下方地图点击取件位置。';$('#pickup-error').textContent='';
      if($('#pickup-coordinates'))$('#pickup-coordinates').textContent='尚未选择位置';
      drawMap();
    }
  };
  form.onsubmit=async e=>{
    e.preventDefault();
    if(!destination){$('#pickup-error').textContent='请先选择有效的公共取件点。';return;}
    if(blocked(destination.x,destination.y)){choose(destination.x,destination.y);return;}
    const body=Object.fromEntries(new FormData(form));
    for(const key of ['quantity','priority','deadline_minutes'])body[key]=Number(body[key]);
    if(destination.id)body.pickup_point_id=destination.id;
    else Object.assign(body,{x:destination.x,y:destination.y,address:destination.name});
    await perform(e.submitter,async()=>{
      try{
        const order=await api('/orders','POST',body);$('#modal').close();
        toast(`订单 ${order.id} 已创建`);await refresh();
      }catch(err){$('#pickup-error').textContent=err.message;throw err;}
    });
  };
  drawMap();
  if(initial){$('#pickup-map-panel').open=true;choose(...initial);}
  bindModal();
}
