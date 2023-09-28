create table city (
    code text primary key not null,
    cname text,
    ename text
);

.mode csv
.import cities.csv city

create table subroute (
    uid text primary key not null,
    dir int,
    cname text,
    ename text,
    main_cname text,
    main_ename text,
    first_stop int, 
    last_stop int, 
    foreign key (first_stop) references stop(uid),
    foreign key (last_stop) references stop(uid)
);

create table stop (
    uid text,
    srt_uid text not null,
    dir int not null,
    station_id int,
    cname text not null,
    ename text,
    sequence int,
    longitude float,
    latitude float,
    primary key (cname, srt_uid, dir),
    foreign key (srt_uid) references subroute(uid)
);
