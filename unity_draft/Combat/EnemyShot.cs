using UnityEngine;

namespace ZGame.UnityDraft.Combat
{
    /// <summary>
    /// Enemy-fired projectile. Inherits Bullet behavior but defaults source to "enemy".
    /// </summary>
    public class EnemyShot : Bullet
    {
        public override void Init(Vector3 pos, Vector2 direction, float dmg, float maxDistance, float spd)
        {
            base.Init(pos, direction, dmg, maxDistance, spd);
            source = "enemy";
        }
    }
}
