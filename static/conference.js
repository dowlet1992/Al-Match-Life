(function(){
    'use strict';
    const node=document.getElementById('conferenceConfig');
    if(!node||!window.LivekitClient)return;
    const config=node.dataset;
    const csrf=config.csrfToken;
    const roomId=config.roomId;
    const isVideo=config.callType==='video';
    const currentEmail=config.currentEmail;
    const isOwner=config.owner===currentEmail;
    const maxParticipants=Number(config.maxParticipants||4);
    let known=[],eligible=[];
    try{known=JSON.parse(config.participants||'[]');eligible=JSON.parse(config.eligible||'[]')}catch(_error){}
    const profileByEmail=new Map(known.map(item=>[item.email,item]));
    let room=null,microphoneOn=true,cameraOn=isVideo;

    function status(text){const box=document.getElementById('conferenceStatus');if(box)box.textContent=text}
    function metadata(participant){try{return JSON.parse(participant.metadata||'{}')}catch(_error){return {}}}
    function participantProfile(participant){
        const meta=metadata(participant);const byName=known.find(item=>item.name===participant.name);
        return byName||{name:participant.name||'NOVIX',avatar:meta.avatar||'/static/app-logo.svg'};
    }
    function ensureTile(participant,local){
        const id='participant-'+participant.identity.replace(/[^a-zA-Z0-9_-]/g,'_');
        let tile=document.getElementById(id);if(tile)return tile;
        const profile=participantProfile(participant);tile=document.createElement('article');tile.className='participant-tile';tile.id=id;
        const fallback=document.createElement('div');fallback.className='participant-fallback';
        const avatar=document.createElement('img');avatar.src=profile.avatar||'/static/app-logo.svg';avatar.alt='';
        const name=document.createElement('strong');name.textContent=profile.name+(local?' · You':'');fallback.append(avatar,name);
        const meta=document.createElement('div');meta.className='participant-meta';
        const label=document.createElement('span');label.textContent=profile.name+(local?' · You':'');
        const states=document.createElement('span');states.className='participant-state';states.innerHTML='<span data-mic>🎙️</span><span data-camera>🎥</span>';meta.append(label,states);tile.append(fallback,meta);
        document.getElementById('participantGrid').appendChild(tile);updateParticipantState(participant);return tile;
    }
    function updateParticipantState(participant){
        const tile=document.getElementById('participant-'+participant.identity.replace(/[^a-zA-Z0-9_-]/g,'_'));if(!tile)return;
        const mic=tile.querySelector('[data-mic]'),camera=tile.querySelector('[data-camera]');
        const micOn=participant.isMicrophoneEnabled!==false,camOn=participant.isCameraEnabled===true;
        mic?.classList.toggle('off',!micOn);camera?.classList.toggle('off',!camOn||!isVideo);camera.hidden=!isVideo;
    }
    function attachTrack(track,publication,participant){
        const tile=ensureTile(participant,participant===room.localParticipant);const element=track.attach();
        if(track.kind===LivekitClient.Track.Kind.Video){element.autoplay=true;element.playsInline=true;tile.prepend(element);tile.querySelector('.participant-fallback').hidden=true}
        else{element.autoplay=true;element.dataset.remoteAudio='true';tile.appendChild(element)}
        updateParticipantState(participant);
    }
    function detachTrack(track){track.detach().forEach(element=>element.remove())}
    function renderParticipant(participant,local){
        ensureTile(participant,local);participant.trackPublications.forEach(publication=>{if(publication.track)attachTrack(publication.track,publication,participant)});
    }
    async function connect(){
        status('Connecting securely…');
        const response=await fetch('/api/conferences/'+encodeURIComponent(roomId)+'/token',{method:'POST',headers:{'X-CSRF-Token':csrf}});
        const data=await response.json();if(!response.ok||!data.ok)throw new Error(data.error||'token_failed');
        room=new LivekitClient.Room({adaptiveStream:true,dynacast:true,disconnectOnPageLeave:true,videoCaptureDefaults:{resolution:LivekitClient.VideoPresets.h720.resolution}});
        room.on(LivekitClient.RoomEvent.TrackSubscribed,attachTrack)
            .on(LivekitClient.RoomEvent.TrackUnsubscribed,detachTrack)
            .on(LivekitClient.RoomEvent.ParticipantConnected,p=>renderParticipant(p,false))
            .on(LivekitClient.RoomEvent.ParticipantDisconnected,p=>document.getElementById('participant-'+p.identity.replace(/[^a-zA-Z0-9_-]/g,'_'))?.remove())
            .on(LivekitClient.RoomEvent.TrackMuted,(_publication,p)=>updateParticipantState(p))
            .on(LivekitClient.RoomEvent.TrackUnmuted,(_publication,p)=>updateParticipantState(p))
            .on(LivekitClient.RoomEvent.ActiveSpeakersChanged,speakers=>{document.querySelectorAll('.participant-tile').forEach(item=>item.classList.remove('speaking'));speakers.forEach(p=>document.getElementById('participant-'+p.identity.replace(/[^a-zA-Z0-9_-]/g,'_'))?.classList.add('speaking'))})
            .on(LivekitClient.RoomEvent.Reconnecting,()=>status('Restoring connection…'))
            .on(LivekitClient.RoomEvent.Reconnected,()=>status('Connection restored'))
            .on(LivekitClient.RoomEvent.Disconnected,()=>status('Call ended'));
        await room.connect(data.url,data.token,{autoSubscribe:true});
        await room.localParticipant.setMicrophoneEnabled(true,{echoCancellation:true,noiseSuppression:true,autoGainControl:true});
        if(isVideo)await room.localParticipant.setCameraEnabled(true,{resolution:LivekitClient.VideoPresets.h720.resolution,frameRate:24});
        renderParticipant(room.localParticipant,true);room.remoteParticipants.forEach(p=>renderParticipant(p,false));
        status('Secure group call · '+(room.remoteParticipants.size+1)+'/'+maxParticipants);
    }
    async function toggleMute(){microphoneOn=!microphoneOn;await room?.localParticipant.setMicrophoneEnabled(microphoneOn);this.classList.toggle('off',!microphoneOn);this.textContent=microphoneOn?'🎙️':'🔇';updateParticipantState(room.localParticipant)}
    async function toggleCamera(){cameraOn=!cameraOn;await room?.localParticipant.setCameraEnabled(cameraOn);this.classList.toggle('off',!cameraOn);this.textContent=cameraOn?'🎥':'🚫';updateParticipantState(room.localParticipant)}
    function renderInviteList(){
        const list=document.getElementById('inviteList');list.replaceChildren();const full=known.length>=maxParticipants;
        eligible.forEach(person=>{const row=document.createElement('div');row.className='invite-person';const img=document.createElement('img');img.src=person.avatar;img.alt='';const name=document.createElement('strong');name.textContent=person.name;const button=document.createElement('button');button.type='button';button.textContent='Invite';button.disabled=full;button.addEventListener('click',()=>invite(person,button));row.append(img,name,button);list.append(row)});
        document.getElementById('inviteEmpty').hidden=eligible.length>0;
    }
    async function invite(person,button){
        button.disabled=true;button.textContent='…';const response=await fetch('/api/conferences/'+encodeURIComponent(roomId)+'/participants',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},body:JSON.stringify({email:person.email})});const data=await response.json();
        if(!response.ok||!data.ok){button.disabled=false;button.textContent='Invite';status(data.error||'Invite failed');return}
        known.push(data.participant);profileByEmail.set(person.email,data.participant);eligible=eligible.filter(item=>item.email!==person.email);renderInviteList();status('Invitation sent · '+known.length+'/'+maxParticipants);
    }
    document.getElementById('conferenceMute')?.addEventListener('click',toggleMute);
    document.getElementById('conferenceCamera')?.addEventListener('click',toggleCamera);
    document.getElementById('conferenceInvite')?.addEventListener('click',()=>{const panel=document.getElementById('invitePanel');panel.hidden=!panel.hidden;renderInviteList()});
    document.getElementById('closeInvite')?.addEventListener('click',()=>document.getElementById('invitePanel').hidden=true);
    document.getElementById('conferenceEnd')?.addEventListener('click',()=>{room?.disconnect();window.location.href='/messages/'+encodeURIComponent(currentEmail)});
    connect().catch(error=>{console.error(error);status('Conference is temporarily unavailable')});
})();
