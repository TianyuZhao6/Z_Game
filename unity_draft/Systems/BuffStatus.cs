using UnityEngine;
using System.Collections.Generic;

namespace ZGame.UnityDraft.Systems
{
    /// <summary>
    /// Tracks temporary buffs for enemies (speed/attack multipliers) with stacking rules.
    /// </summary>
    public class BuffStatus : MonoBehaviour
    {
        private class Buff
        {
            public float speedMult;
            public float attackMult;
            public float duration;
        }

        private readonly List<Buff> _buffs = new();
        private Enemy _enemy;
        private float _baseSpeed;
        private int _baseAttack;

        private void Awake()
        {
            _enemy = GetComponent<Enemy>();
            if (_enemy != null)
            {
                _baseSpeed = _enemy.speed;
                _baseAttack = _enemy.attack;
            }
        }

        public void ApplyBuff(float speedMult, float attackMult, float duration, int maxStacks)
        {
            _buffs.Add(new Buff { speedMult = speedMult, attackMult = attackMult, duration = duration });
            if (maxStacks > 0 && _buffs.Count > maxStacks)
            {
                _buffs.RemoveAt(0);
            }
            Recompute();
        }

        private void Update()
        {
            float dt = Time.deltaTime;
            bool changed = false;
            for (int i = _buffs.Count - 1; i >= 0; i--)
            {
                _buffs[i].duration -= dt;
                if (_buffs[i].duration <= 0f)
                {
                    _buffs.RemoveAt(i);
                    changed = true;
                }
            }
            if (changed) Recompute();
        }

        private void Recompute()
        {
            if (_enemy == null) return;
            float speedMul = 1f;
            float atkMul = 1f;
            foreach (var b in _buffs)
            {
                speedMul *= b.speedMult;
                atkMul *= b.attackMult;
            }
            _enemy.speed = _baseSpeed * speedMul;
            _enemy.attack = Mathf.Max(1, Mathf.RoundToInt(_baseAttack * atkMul));
        }
    }
}
