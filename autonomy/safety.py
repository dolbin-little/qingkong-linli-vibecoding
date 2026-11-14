"""Independent software guard. Never disarm in flight, never bypass autopilot checks."""
from .models import norm,finite_vector
import math
from .planning import safe_segment,safe_point

class SafetyGuard:
    def check(self,t,s,now,command=None):
        if not math.isfinite(t.battery) or not 0<=t.battery<=100:return 'INVALID_BATTERY','HOLD'
        if any(not math.isfinite(x) or x>now+.2 for x in (t.heartbeat_at,t.position_at,t.sensor_at,t.battery_at,t.gps_at)):return 'INVALID_TIMESTAMP','HOLD'
        if now-t.heartbeat_at>2.:return 'LINK_LOSS','LAND'
        if now-t.position_at>.8:return 'POSITION_STALE','HOLD'
        if t.gps_fix<3 or t.satellites<6 or t.satellites==255:return 'POSITION_QUALITY','LAND'
        if now-t.gps_at>2.:return 'GPS_STALE','HOLD'
        if now-t.battery_at>3.:return 'BATTERY_STALE','HOLD'
        if now-t.sensor_at>1.:return 'PERCEPTION_STALE','HOLD'
        if not finite_vector(t.position) or not finite_vector(t.velocity):return 'INVALID_STATE','HOLD'
        if not safe_point(t.position,s,margin=1.):return 'GEOFENCE','HOLD'
        if t.battery<=15:return 'BATTERY_CRITICAL','LAND'
        if t.battery<=25:return 'BATTERY_RESERVE','RTL'
        speed=norm(t.velocity)
        if t.nearest<max(2.8,speed*speed/(2*1.8)+1.2):return 'OBSTACLE_NEAR','HOLD'
        if command is not None:
            if not finite_vector(command) or norm(command)>4.5:return 'INVALID_COMMAND','HOLD'
            ahead=[p+v*1.2 for p,v in zip(t.position,command)]
            if not safe_segment(t.position,ahead,s):return 'CORRIDOR_LIMIT','HOLD'
        return None,None

    def preflight(self,t,s,now):
        reason,_=self.check(t,s,now)
        if reason:return False,reason
        if t.armed:return False,'ALREADY_ARMED'
        if t.battery<45:return False,'INSUFFICIENT_RETURN_RESERVE'
        if norm(s['wind'])>6:return False,'WIND_LIMIT'
        return True,'检查通过'
