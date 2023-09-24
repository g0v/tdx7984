create table city (
    code text primary key not null,
    cname text,
    ename text
);

.mode csv
.import cities.csv city

create table subroute (
    uid text primary key not null,
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
    uid int primary key not null,
    subroute text,
    station_id int,
    cname text,
    ename text,
    longitude float,
    latitude float,
    foreign key (subroute) references subroute(uid)
);
